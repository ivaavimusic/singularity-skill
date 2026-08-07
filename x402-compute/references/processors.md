# SGL Processors

Deploy one function; get a paid HTTP endpoint and a live MCP server.

**Status:** built and tested end to end on production with real USDC. Publishing is not open yet —
`PROCESSORS_PAYMENTS_ENABLED` and `PROCESSORS_RUNTIME_BILLING_ENABLED` are off. Do not tell a user
they can publish today.

**Base URL:** `https://processors.x402compute.cc`

## The model, in one paragraph

A processor is a single typed function we host. The BUYER pays the PUBLISHER **directly** in USDC
over x402 — Singularity never holds it and takes **no cut of sales**. The PUBLISHER pays us for
compute instead: before each run we hold the maximum it could cost (derived from the `timeout_ms`
they declared) and rebate the unused part afterwards. That is the platform's only revenue.

Not a TEE. Execution is an isolated V8 sandbox on Cloudflare's edge — same isolation model as a
Worker. For hardware-attested confidentiality use SGL Grid or a confidential Machine instead.
An older version of the docs claimed TEE; it was wrong.

## Publisher flow (CLI)

```bash
npm i -g @singularity-layer/cli
singularity processors init <slug>     # scaffolds processor.json + processor.js
singularity processors deploy          # prints the invoke token ONCE
singularity processors run '{"x":1}'   # owner run
singularity processors logs            # runs + failure rate
singularity processors publish         # list it publicly
singularity processors earnings        # sales (to their wallet) + compute spend
```

Auth is a Solana wallet signature; the key never leaves the machine.

## Manifest essentials

```json
{
  "slug": "…", "name": "…", "description": "…",
  "lane": "managed",
  "price_usd": "0.01",
  "input_schema": {…}, "output_schema": {…},
  "limits": { "timeout_ms": 5000, "cpu_ms": 1000, "subrequests": 1 },
  "egress": { "allow": ["api.example.com"] },
  "secrets": [{ "name": "KEY", "hosts": ["api.example.com"],
                "inject": { "header": "Authorization", "format": "Bearer {value}" } }],
  "inference": { "provider": "singularity", "model": "qwen-2.5-7b", "api_key_secret": "KEY" }
}
```

Rules that bite:
- `limits.subrequests` must be >= 1; `timeout_ms` <= 600000; `cpu_ms` <= 30000.
- Every host in `secrets[].hosts` must ALSO appear in `egress.allow`.
- `inject.format` must contain the literal `{value}` placeholder.
- Slugs are lowercase, permanent, and never reusable.
- Egress rejects wildcards, `host:port`, URLs, IP literals, and internal names.

## Grid inference from inside a processor

Declare `inference.provider: "singularity"`, allowlist `grid.x402compute.cc`, and store a compute
API key (`x402c_…`) as the named secret. The gateway injects it on egress — the isolate never sees
it. Then just call the OpenAI-compatible endpoint:

```js
await fetch('https://grid.x402compute.cc/v1/chat/completions', {
  method: 'POST', headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ model: 'qwen-2.5-7b', messages: [...] }),
});
```

Grid usage bills the KEY OWNER's credits, separately from processor runtime.

## Calling a processor

| Caller | Header | Who pays |
|---|---|---|
| Anonymous buyer | `X-Payment` (x402) | buyer pays publisher; publisher pays runtime |
| Publisher's own product | `Authorization: Bearer sk-sglproc_…` | publisher pays runtime only |
| Owner | wallet signature | publisher pays runtime only |

No credential on a paid processor returns `402` with x402 requirements whose `payTo` is the
**publisher's** wallet.

Long runs return `202` + `poll_url` + run token; send `Prefer: respond-async` to skip the wait.

## MCP

`POST /processors/<slug>/mcp` is a stateless MCP server (2026-07-28; `initialize` also answered for
2025 clients). `server/discover`, `tools/list` and `ping` are free; `tools/call` is charged and
accepts the same `X-Payment` / bearer headers. `GET` on that path returns a descriptor;
`GET` with `Accept: text/event-stream` returns 405 (no SSE — it is stateless).

## Billing rules to state accurately

- A run that RAN and failed is **billed** — the compute was spent. It counts in the public failure rate.
- A run that never started because of a platform fault is **refunded in full**, automatically.
- Refused before starting (no input, concurrency cap, insufficient balance) — **nothing held**.
- No minimum price. Publishers may charge anything, including less than compute costs; that is
  their decision and the dashboard shows them the margin.

## Gotcha worth warning users about

A publisher's payout wallet must already be able to receive USDC. Solana cannot transfer a token to
an account that does not exist, and the x402 payer does not create one — so a brand-new wallet's
first sale would fail. Publishing is refused with instructions: send any USDC to the wallet once.
