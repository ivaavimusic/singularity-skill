#!/usr/bin/env python3
"""End-to-end wire tests for the x402-compute paying scripts, with the network mocked.

Every key is generated at runtime; nothing here moves money or talks to a server.
Checks, for Base, Robinhood AND Solana:
- a v2 PAYMENT-REQUIRED header is answered with PAYMENT-SIGNATURE (accepted echoed unchanged,
  inner payload signed for exactly `amount` to exactly `payTo`);
- no header, or X402_WIRE=v1, sends X-Payment v1 exactly as before;
- a 5xx or timeout after paying is pending and nothing is signed or sent again;
- train_x402 saves the header NAME with the payment and `resume` resends the identical header.

Run: python3 -m unittest discover -s tests -v   (from the repo root: python3 -m unittest discover -s tests/x402-compute -t .)
"""

import base64
import json
import os
import struct
import sys
import tempfile
import unittest
import uuid
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.environ.get("X402_WIRE_SCRIPTS") or os.path.join(HERE, "..", "..", "x402-compute", "scripts"))
sys.path.insert(0, SCRIPTS)

try:
    import requests
    from eth_account import Account
    from solders.hash import Hash
    from solders.keypair import Keypair
    from solders.transaction import VersionedTransaction
    HAVE_DEPS = True
except Exception:  # pragma: no cover
    HAVE_DEPS = False

import x402_wire as w  # noqa: E402

SOLANA_CAIP2 = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"
ASSETS = {
    "base": ("eip155:8453", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", {"name": "USD Coin", "version": "2"}),
    "robinhood": ("eip155:4663", "0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168", {"name": "Global Dollar", "version": "1"}),
    "solana": (SOLANA_CAIP2, "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", None),
}


class _Headers(dict):
    def get(self, key, default=None):
        for k, v in self.items():
            if k.lower() == str(key).lower():
                return v
        return default


class _Resp:
    def __init__(self, status_code, body=None, headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = _Headers(headers or {})
        self.text = json.dumps(body)

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


@unittest.skipUnless(HAVE_DEPS, "skill dependencies (requests, eth_account, solders) not installed")
class ComputePayWire(unittest.TestCase):
    def setUp(self):
        self.evm = Account.create()
        self.sol = Keypair()
        self.fee_payer = str(Keypair().pubkey())
        self.pay_to = {"base": Account.create().address, "robinhood": Account.create().address,
                       "solana": str(Keypair().pubkey())}
        self.env = mock.patch.dict(os.environ, {
            "PRIVATE_KEY": self.evm.key.hex(),
            "WALLET_ADDRESS": self.evm.address,
            "SOLANA_SECRET_KEY": json.dumps(list(bytes(self.sol))),
        })
        self.env.start()
        for k in ("X402_WIRE", "SOLANA_WALLET_ADDRESS", "WALLET_ADDRESS_SECONDARY", "OWS_WALLET", "COMPUTE_AUTH_MODE"):
            os.environ.pop(k, None)
        self.sent = []
        self.amount = "2500000"
        self.extra_body = {}

    def tearDown(self):
        self.env.stop()

    def _offer(self, network):
        caip2, asset, extra = ASSETS[network]
        if network == "solana":
            extra = {"feePayer": self.fee_payer}
        v1 = {"scheme": "exact", "network": network, "maxAmountRequired": self.amount, "payTo": self.pay_to[network],
              "asset": asset, "maxTimeoutSeconds": 3600, "extra": extra}
        v2 = {"scheme": "exact", "network": caip2, "asset": asset, "amount": self.amount, "payTo": self.pay_to[network],
              "maxTimeoutSeconds": 3600, "extra": extra}
        return v1, v2

    def _server(self, network, emit_v2=True, paid_status=200, paid_body=None):
        v1, v2 = self._offer(network)
        self.required = {"x402Version": 2, "resource": {"url": "https://compute.x402layer.cc/compute/provision"},
                         "accepts": [v2]}

        def post(url, *args, **kwargs):
            headers = kwargs.get("headers") or {}
            paid = {k: v for k, v in headers.items() if k.lower() in ("payment-signature", "x-payment")}
            if not paid:
                hdrs = {"PAYMENT-REQUIRED": w.encode_header(self.required)} if emit_v2 else {}
                return _Resp(402, dict({"x402Version": 1, "accepts": [v1]}, **self.extra_body), hdrs)
            self.sent.append(paid)
            if paid_status == "timeout":
                raise requests.Timeout("read timed out")
            return _Resp(paid_status, paid_body if paid_body is not None else {"order": {"id": "o-1"}})
        return post

    def _patches(self, post):
        import solana_signing
        return [
            mock.patch("requests.post", side_effect=post),
            mock.patch.object(solana_signing, "_get_recent_blockhash", lambda _cls: Hash.new_unique()),
            mock.patch.object(solana_signing, "_rpc_call", lambda method, params: {"value": None}),
            mock.patch.object(solana_signing, "_account_exists", lambda _pk: True),
        ]

    def _run(self, fn, network, **kw):
        post = self._server(network, **kw)
        patches = self._patches(post)
        for p in patches:
            p.start()
        try:
            return fn()
        finally:
            for p in reversed(patches):
                p.stop()

    def _provision(self, network):
        import provision
        with mock.patch.object(provision, "create_compute_auth_headers", lambda *a, **k: {}):
            return provision.provision_instance("plan-x", "ewr", network=network, skip_confirm=True)

    def _assert_v2(self, network):
        self.assertEqual(len(self.sent), 1)
        (name, value), = self.sent[0].items()
        self.assertEqual(name, "PAYMENT-SIGNATURE")
        env = w.decode_header(value)
        self.assertEqual(env["x402Version"], 2)
        self.assertEqual(env["accepted"], self.required["accepts"][0])
        if network == "solana":
            tx = VersionedTransaction.from_bytes(base64.b64decode(env["payload"]["transaction"]))
            self.assertEqual(str(tx.message.account_keys[0]), self.fee_payer)
            data = bytes(tx.message.instructions[-1].data)
            self.assertEqual(struct.unpack("<Q", data[1:9])[0], int(self.amount))
        else:
            auth = env["payload"]["authorization"]
            self.assertEqual([auth["value"], auth["to"], auth["from"]], [self.amount, self.pay_to[network], self.evm.address])

    def _assert_v1(self, network):
        self.assertEqual(len(self.sent), 1)
        (name, value), = self.sent[0].items()
        self.assertEqual(name, "X-Payment")
        decoded = json.loads(base64.b64decode(value))
        self.assertEqual([decoded["x402Version"], decoded["scheme"], decoded["network"]], [1, "exact", network])

    def test_provision_v2_all_networks(self):
        for network in ("base", "robinhood", "solana"):
            with self.subTest(network=network):
                self.sent = []
                out = self._run(lambda: self._provision(network), network)
                self.assertEqual(out, {"order": {"id": "o-1"}})
                self._assert_v2(network)

    def test_provision_v1_without_header_and_forced(self):
        for network in ("base", "robinhood", "solana"):
            with self.subTest(network=network, mode="no header"):
                self.sent = []
                self._run(lambda: self._provision(network), network, emit_v2=False)
                self._assert_v1(network)
        os.environ["X402_WIRE"] = "v1"
        self.sent = []
        self._run(lambda: self._provision("base"), "base")
        self._assert_v1("base")

    def test_provision_wrong_v2_asset_signs_nothing(self):
        def bad_asset_server(*a, **k):
            return post(*a, **k)
        post = self._server("base")
        self.required["accepts"][0]["asset"] = "0x0000000000000000000000000000000000000001"
        patches = self._patches(bad_asset_server)
        for p in patches:
            p.start()
        try:
            with self.assertRaises(ValueError):
                self._provision("base")
        finally:
            for p in reversed(patches):
                p.stop()
        self.assertEqual(self.sent, [])

    def test_provision_pending_never_resigns(self):
        for status in (500, 503, "timeout"):
            with self.subTest(status=status):
                self.sent = []
                out = self._run(lambda: self._provision("base"), "base", paid_status=status)
                self.assertTrue(out.get("pending"))
                self.assertEqual(len(self.sent), 1)

    def test_extend_v2_base_and_solana(self):
        import extend_instance
        for network in ("base", "solana"):
            with self.subTest(network=network):
                self.sent = []
                with mock.patch.object(extend_instance, "create_compute_auth_headers", lambda *a, **k: {}):
                    self._run(lambda: extend_instance.extend_instance("i-1", 24, network=network, skip_confirm=True), network)
                self._assert_v2(network)

    def test_train_saves_header_and_resume_resends_identical(self):
        import train_x402
        quote_id = str(uuid.uuid4())
        self.extra_body = {"singularity": {"quote_id": quote_id, "price_usd": 2.5}}
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(train_x402, "PENDING_DIR", tmp), \
                    mock.patch.object(train_x402, "create_compute_auth_headers", lambda *a, **k: {}):
                for network in ("base", "solana"):
                    with self.subTest(network=network):
                        self.sent = []
                        out = self._run(lambda: train_x402.run("ds-1", "m", "g", 1, network=network, skip_confirm=True),
                                        network, paid_status=202, paid_body={"claim_token": "ct", "quote_id": quote_id})
                        self.assertEqual(out.get("claim_token"), "ct")
                        self._assert_v2(network)
                        with open(train_x402._pending_path(quote_id)) as fh:
                            saved = json.load(fh)
                        self.assertEqual(saved["payment_header"], "PAYMENT-SIGNATURE")
                        first = self.sent[0]
                        self.sent = []
                        self._run(lambda: train_x402.resume(quote_id), network, paid_status=202,
                                  paid_body={"quote_id": quote_id})
                        self.assertEqual(self.sent, [first])

    def test_train_resume_of_old_v1_save_uses_x_payment(self):
        import train_x402
        quote_id = str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(train_x402, "PENDING_DIR", tmp):
                path = train_x402._pending_path(quote_id)
                train_x402._makedirs_durable(tmp)
                train_x402._write_durable(path, {"body": {"quote_id": quote_id}, "x_payment": "djE="})
                self._run(lambda: train_x402.resume(quote_id), "base", paid_status=202, paid_body={})
                self.assertEqual(self.sent, [{"X-Payment": "djE="}])


if __name__ == "__main__":
    unittest.main()
