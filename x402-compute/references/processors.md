# SGL Processors

Deploy one function; get a paid HTTP endpoint, an OpenAPI document, and a live MCP server.

**Status:** LIVE. Buyer payments (`PROCESSORS_PAYMENTS_ENABLED`) and publisher runtime billing
(`PROCESSORS_RUNTIME_BILLING_ENABLED`) are both ON, and the API and CLI are fully usable. The
**dashboard UI is still dark** (`NEXT_PUBLIC_ENABLE_PROCESSORS=false` in the cloud app), so publish and
manage through the CLI. An earlier version of this file said publishing was not open — that is out of
date; do not repeat it.

**Base URL:** `https://processors.x402compute.cc`

## The model, in one paragraph

A processor is a function we host. The BUYER pays the PUBLISHER **directly** in USDC over x402 —
Singularity never holds it and takes **no cut of sales**. The PUBLISHER pays us for compute instead:
before each run we hold the maximum it could cost (derived from the `timeout_ms` they declared) and
rebate the unused part afterwards. That is the platform's only revenue.

Not a TEE. Execution is an isolated V8 sandbox on Cloudflare's edge — the same isolation model as a
Worker. For hardware-attested confidentiality use SGL Grid or a confidential Machine instead. An older
version of these docs claimed TEE; it was wrong.

## Publisher flow (CLI)

```bash
npm i -g @singularity-layer/cli          # package is scoped; the command is `singularity`
singularity processors init <slug>       # scaffolds processor.json + processor.js
singularity processors deploy            # prints the invoke token ONCE
singularity processors run '{"x":1}'     # owner run
singularity processors call -i           # prompts per field, from your own input_schema
singularity processors logs              # runs + failure rate; --follow to tail
singularity processors publish           # list it publicly, instantly, no review
singularity processors revenue           # sales + compute across everything you own
singularity processors pause | resume    # stop traffic WITHOUT losing the slug
```

Auth is a Solana wallet signature; the key never leaves the machine.

## TypeScript and npm packages

```bash
npm i zod
singularity processors deploy --bundle --entry processor.ts
```

`--bundle` runs esbuild **on the publisher's machine**. We never run `npm install` for them: a
postinstall script is arbitrary code, and running it on infrastructure holding platform credentials is
not something scanning makes safe. The bundle crosses the boundary; `node_modules` never does.

The bundler targets a Worker isolate, so a dependency reaching for `fs`, `child_process` or raw sockets
fails at deploy time on their terminal — naming the importer — rather than inside a run a buyer already
paid for.

Going back to a single file needs `--no-bundle`: a stored bundle keeps winning at load time, so plain
`code` would silently never take effect, and the server refuses the ambiguous update rather than
accepting it.

## Manifest essentials

```json
{
  "slug": "…", "name": "…", "description": "…",
  "lane": "managed",
  "price_usd": "0.01",
  "methods": ["GET", "POST"],
  "input_schema": {…}, "output_schema": {…},
  "limits": { "timeout_ms": 5000, "cpu_ms": 1000, "subrequests": 1 },
  "egress": { "allow": ["api.example.com"] },
  "secrets": [
    { "name": "KEY", "hosts": ["api.example.com"],
      "inject": { "header": "Authorization", "format": "Bearer {value}" } },
    { "name": "SIGNING_KEY", "mode": "env" }
  ],
  "pricing": {
    "mode": "computed", "base_usd": "0.01",
    "units": [{ "field": "items", "measure": "length", "per_unit_usd": "0.005" }],
    "max_usd": "1.00"
  },
  "inference": { "provider": "singularity", "model": "qwen-2.5-7b", "api_key_secret": "KEY" }
}
```

Rules that bite:
- `limits.subrequests` must be >= 1; `timeout_ms` <= 600000; `cpu_ms` <= 30000.
- Every host in `secrets[].hosts` must ALSO appear in `egress.allow`.
- `inject.format` must contain the literal `{value}` placeholder.
- Slugs are lowercase, permanent, and never reusable — `pause` exists so nobody burns one to stop traffic.
- Egress rejects wildcards, `host:port`, URLs, IP literals, and internal names.
- `sgl-ctx.internal` must NOT be allowlisted. It is reserved for processor state and needs no entry.

## Secrets: two modes, and the difference is the point

`inject` (the DEFAULT) — the value **never enters the isolate**. Code calls `fetch()` with no
credential and the egress gateway adds the header server-side, for the declared hosts and nowhere else.
The permitted claim is: the key is held by our egress gateway and is not readable from the code's
environment. DO NOT say it cannot be leaked — publisher code can still SPEND it against an allowlisted
host, and a host that echoes request headers hands the value straight back.

`mode: "env"` — the value IS readable by the publisher's code, via `await SGL.secrets.get('NAME')`.
This is a real downgrade and is opt-in per secret. Once the value is in the isolate it can be printed
into their captured logs or sent to any host in their egress allowlist, and we cannot stop either. It is
readable by EVERY BUNDLED DEPENDENCY too, not just the code they wrote — anything in that isolate can
call `SGL.secrets.get()`. It exists because refusing it is worse: a key used to sign something locally
has no outbound header to be injected into, and the alternative people reach for is hard-coding it.

**An inject-mode secret is NOT readable via `SGL.secrets.get()`** — it returns null, exactly as for a
name that was never declared. Never tell a user to read an injected secret from their code.

`singularity processors env list` shows which of theirs is which.

## Processor state

A processor is a fresh isolate every run, so anything kept between runs goes here. None of it needs an
`egress.allow` entry — it is not the network.

```js
// Key/value: a cursor, a cache, a dedupe set. Opaque strings, byte-exact both ways.
await SGL.kv.put('cursor', '2026-08-12');
const cursor = await SGL.kv.get('cursor');

// Compare-and-swap, because concurrent runs of one processor are normal, not an edge case.
const cur = await SGL.kv.getWithVersion('count');
await SGL.kv.put('count', String(Number(cur.value) + 1), { ifVersion: cur.version });
// A mismatch throws with err.code === 'version_conflict' and err.currentVersion. Re-read and retry.

// Objects: a generated PDF, an image, a dataset.
await SGL.files.put('reports/august.pdf', bytes, { contentType: 'application/pdf' });
const { url } = await SGL.files.downloadUrl('reports/august.pdf', { ttlSeconds: 3600 });
```

Limits: 10,000 keys, 1 KiB key, 64 KiB value; 100 MiB of files, 10 MiB per object, 10,000 objects.
`SGL.kv.list()` and `SGL.files.list()` paginate and never return values.

`downloadUrl` is a signed expiring link a buyer can fetch with **no credential**. It is always served
as an attachment with a forced `application/octet-stream` type — the publisher's declared type is never
echoed — so a stored HTML or SVG file cannot execute. Treat it as a **bearer link**: anyone who obtains
it can download until it expires (default 1h, max 24h), so it must not be logged, put in a public page,
or sent anywhere the file itself would not be sent.

State is deleted when the processor is deleted.

## Console output

`console.log` / `warn` / `error` from inside a run is captured and readable per run:

```bash
singularity processors logs                    # the run list
singularity processors logs --logs <run_id>    # that run's own output
```

Every `console.log/warn/error/info/debug` call is captured, capped, stripped of terminal escape
sequences, and deleted with the run after 30 days. Best-effort observability, never evidence: it records
what the code asked `console` to print, and publisher code can bypass the shim. Anything they printed is
there — including anything a caller sent them, if they printed it.

## Pricing: flat, or computed from the input

Flat is the default: `price_usd` and nothing else.

With a `pricing` block the price depends on the buyer's own input. It is a **declarative formula, never
publisher code** — running their code to price a request would be unpaid execution available to anyone
sending a probe, and would let the price depend on a clock or a counter, so a buyer could be quoted one
number and charged another.

- `measure`: `length` (array length), `bytes` (UTF-8 byte length of a string), `value` (a number the
  buyer supplies). `unit_size` charges per N units, rounded UP.
- `field` is a **top-level** key of `input`. No paths.
- `max_usd` is REQUIRED — it is how a buyer bounds what they agree to.
- `base_usd` must equal `price_usd`, and `price_usd` is then the **FLOOR**, not the price. The
  catalogue reports `price_varies`, and the OpenAPI/MCP annotation carries
  `amount_is_minimum`, `min`, `max` and the full formula.

To get the exact price: send a 402 request with the input you intend to use. The response carries
`quote`, `quote_usd` and the formula. Echoing `X-SGL-Quote: <quote>` when paying is optional; a
mismatch is a 409 that charges nothing, which protects a buyer whose input changed after quoting.

Changing the input between the quote and the payment cannot underpay: the price is recomputed and the
payment is rejected.

## Grid inference from inside a processor

Declare `inference.provider: "singularity"`, allowlist `grid.x402compute.cc`, and store a compute API
key (`x402c_…`) as the named secret. The gateway injects it on egress — the isolate never sees it.

```js
await fetch('https://grid.x402compute.cc/v1/chat/completions', {
  method: 'POST', headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ model: 'qwen-2.5-7b', messages: [...] }),
});
```

Grid usage bills the KEY OWNER's credits, separately from processor runtime.

## Which chain a buyer pays on, and what the publisher must declare

Three chains. The publisher chooses which of them their processor accepts; the default is Solana alone.

| Chain | Asset | Publisher's payout address |
|---|---|---|
| `solana` | USDC (`EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`) | base58 wallet — **the default**, taken from the deploying wallet |
| `base` | USDC (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`) | `0x…` |
| `robinhood` | USDG (`0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168`) | `0x…` |

MegaETH is **not** a processor rail, even though the platform settles it for Machines and credit top-ups.

A manifest with no `payout` block is paid in USDC on Solana at the deploying wallet, which is how every
processor worked before this existed. To accept more:

```json
{
  "price_usd": "0.01",
  "payout": {
    "solana": "<base58 wallet>",
    "base": "0x…",
    "robinhood": "0x…"
  }
}
```

**ONE `price_usd` IS THE PRICE ON EVERY CHAIN.** All three assets are 6-decimal stablecoins, so $0.01 is
`10000` micro-units whichever one settles. There is no per-chain price and no conversion.

### Robinhood is offered ON REQUEST, and this matters if you write a client

The 402 lists **Solana and Base** by default. **Robinhood is withheld unless you ask for it**, with:

```
X-Accept-Networks: solana,base,robinhood
```

WHY, because it is not arbitrary: the reference x402 client validates the WHOLE `accepts` array against a
fixed list of chain names and throws on the first one it does not recognise, instead of skipping that
entry. Robinhood is Singularity's own self-facilitated rail and is not on that list. So including it
unprompted stops a conformant buyer paying on Solana or Base either — chains they hold, that were on
offer. Sending the header says "I parse the array myself".

Robinhood payments work exactly as before; nothing about settlement changed. And a processor paid ONLY on
Robinhood advertises it regardless — hiding it would leave an empty 402.

### What this means for a buyer

The 402 carries **one `accepts` entry per chain that processor accepts**, so read the array rather than
assuming a single entry. Match on `network` — `solana`, `base`, or `robinhood` (the CAIP-2 spellings
`eip155:8453` and `eip155:4663` are also accepted on the way in) — pick the one the wallet can sign for,
and pay that entry. `maxAmountRequired` is identical on all of them.

A network the processor did not declare is refused at settlement, not silently accepted: the buyer's
`network` selects one of OUR offered rows and is never trusted for the asset, the amount, or the
recipient.

### What still has to be Solana

| | |
|---|---|
| Owner / CLI auth | **Solana wallet signature.** The worker answers 501 for any other chain rather than trusting an address header. Separate from how the publisher is paid. |
| The `canReceiveUsdc` publish check | **Solana only.** Solana cannot transfer an SPL token to an account that does not exist, so publishing is refused until the Solana payout wallet holds a USDC token account. Base and Robinhood have no equivalent requirement. |
| Publisher's own runtime cost | Credits, which can be topped up on any of the platform's four rails. |

### Refunds do not exist, and an agent must not promise one

**A processor payment is final.** The buyer's funds move directly to the publisher's wallet; the platform
is never the recipient and holds nothing, so there is nothing for it to return. Do not tell a user a
failed run can be refunded.

What to do instead when a paid run does not deliver:

1. **Re-send the request with the SAME `X-Payment` header.** It returns the run that payment already
   bought and does NOT charge again. This is the recovery path for every failure mode — bad code, a
   platform fault, or a response lost in flight. The `run_id` from the original response identifies it.
2. **Before paying, read `failure_rate_30d`** on the catalogue entry. Platform faults are excluded from
   it, so it measures the publisher's own code. That is the buyer's protection, in place of a refund.

The publisher's held compute cost IS returned to them when the platform is at fault — that is a separate
flow and does not involve the buyer.

### Address rules that cost money to get wrong

- Addresses are stored **exactly as written**. Never normalise or lowercase one.
- A mixed-case `0x` address is validated against its **EIP-55 checksum**; deploy names the address it
  thinks was meant. An all-lowercase `0x` address carries no checksum and is accepted as written.
- A Solana address is checked as base58 and decoded to confirm 32 bytes. There is **no** way to detect a
  lowercased Solana address — base58 is case-sensitive and lowercase letters are legal in it, so a folded
  wallet is a different, still-valid-looking account. Do not case-fold one, ever.
- Payments are irreversible and go straight to the publisher. Tell a user to paste an address, not retype
  it.

## Calling a processor

| Caller | Header | Who pays |
|---|---|---|
| Anonymous buyer | `X-Payment` (x402) | buyer pays publisher; publisher pays runtime |
| Publisher's own product | `Authorization: Bearer sk-sglproc_…` | publisher pays runtime only |
| Owner | wallet signature | publisher pays runtime only |

No credential on a paid processor returns `402` with x402 requirements whose `payTo` is the
**publisher's** wallet.

A processor may answer `GET` as well as `POST` (`methods` in the manifest, both by default). On a GET
the input is the query string, and the payment `resource` includes it — so a 402 quoted for
`?amount=1` cannot be paid with `?amount=1000000`.

Long runs return `202` + `poll_url` + run token; send `Prefer: respond-async` to skip the wait.

A **paused** processor returns 404 to anonymous buyers (no 402 is issued, so nobody pays for work that
will be refused) and 503 `paused` to invoke-token callers. The owner can still run it, which is how a
publisher verifies a fix before resuming.

## MCP

`POST /processors/<slug>/mcp` is a stateless MCP server (2026-07-28; `initialize` also answered for
2025 clients). `server/discover`, `tools/list` and `ping` are free; `tools/call` is charged and accepts
the same `X-Payment` / bearer headers. `GET` on that path returns a descriptor; `GET` with
`Accept: text/event-stream` returns 405 (no SSE — it is stateless).

## Billing rules to state accurately

- A run that RAN and failed is **billed** — the compute was spent. It counts in the public failure rate.
- A run that never started because of a platform fault is **refunded in full**, automatically, and is
  excluded from the failure rate.
- Refused before starting (no input, concurrency cap, insufficient balance, wrong method, paused) —
  **nothing held**.
- No minimum price beyond "greater than zero once payments are armed". Publishers may charge less than
  compute costs; that is their decision.

## Gotchas worth warning users about

A publisher's payout wallet must already be able to receive USDC. Solana cannot transfer a token to an
account that does not exist, and the x402 payer does not create one — so a brand-new wallet's first
sale would fail. Publishing is refused with instructions: send any USDC to the wallet once.

Unlisting is NOT stopping. An unlisted processor is out of the catalogue but its endpoint keeps
answering anyone holding the URL or an invoke token; those calls earn the publisher nothing and still
draw COMPUTE from their credit balance. `pause` is the switch that stops traffic; `delete` is permanent
and burns the slug forever. Note an owner-signed run on a PAUSED processor still costs compute — a run
costs us the same whoever triggered it.
