# Coding sandboxes for your platform

Give each of **your** users their own coding sandbox (Claude Code, Codex, OpenCode or Pi on a small
private computer that sleeps when idle), created and paid for by your platform through our API.
You tag every sandbox with your own customer id, cap what you spend, get webhooks, and can embed a
sandbox's terminal in your own app with no Singularity Layer branding.

Base URL: `https://compute.x402layer.cc/pods/v1`. Auth: a compute API key (`X-API-Key: x402c_...`)
with **`pods:control:write`** (a sandbox runs commands) and **`spend`**, or a wallet signature.

---

## Price: pay as you go, from your credits

| What | Price |
|------|-------|
| Awake time | **$0.012 per hour**, charged when each hour starts |
| Disk (12 GB, kept while asleep) | **$1.50 a month per sandbox**, charged as $0.05 per started day |
| Our models (OpenCode, Pi) | per call from credits, as everywhere else |
| Your users' own keys (any harness) | free on our side |

A sandbox sleeps after 15 idle minutes and wakes on the next request in about 2 seconds, so a user
who works 2 hours a day costs about $0.72 + $1.50 = **$2.22 a month**. No monthly base fee.

Each sandbox: 2 vCPU, 4 GB memory, 12 GB disk.

---

## 1. Set your platform up (once)

```bash
curl -X PUT https://compute.x402layer.cc/pods/v1/platform \
  -H "X-API-Key: $SGL_API_KEY" -H "content-type: application/json" \
  -d '{"monthly_cap_usd": 200, "end_user_monthly_cap_usd": 10, "max_live_per_end_user": 2,
       "white_label": true, "embed_origins": ["https://app.example.com"]}'
```

| Field | Meaning |
|-------|---------|
| `monthly_cap_usd` | Hard stop for your whole platform per calendar month (UTC). Default $50. |
| `end_user_monthly_cap_usd` | Hard stop per end user per month (`null` = none). |
| `max_live_per_end_user` | Live sandboxes one end user may have (up to your platform limit). |
| `white_label` | Neutral names inside the sandbox (no Singularity Layer). |
| `embed_origins` | The https origins allowed to frame the embedded terminal. |
| `enabled` | `false` stops new sandboxes (existing ones keep running). |

`GET /platform` shows these, this month's spend, and your live-sandbox limit (`max_live`, set by us:
ask to raise it).

Per-user overrides: `PUT /platform/end-users/{end_user_id}` with `{"monthly_cap_usd": 25, "max_live": 3}`,
`GET` to read it with that user's spend, `DELETE` to go back to the defaults.

---

## 2. Create a sandbox for one of your users

```bash
curl -X POST https://compute.x402layer.cc/pods/v1/sandboxes \
  -H "X-API-Key: $SGL_API_KEY" -H "content-type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"harness": "opencode", "ai_mode": "managed",
       "end_user_id": "cust_8341", "tags": {"plan": "pro", "team": "acme"}}'
```

- `Idempotency-Key` is required: retry with the SAME key and you get the same sandbox, never a
  second charge.
- `harness`: `claude-code`, `codex`, `opencode`, `pi`. `ai_mode`: `managed` (our models from your
  credits; OpenCode and Pi), `own_key` (`api_key`, and for OpenCode/Pi `base_url` + `model`). Claude
  Code runs only on the user's own Anthropic key or their own sign-in in the terminal.
- `end_user_id`: your id for the user (1 to 128 of `A-Z a-z 0-9 . _ : @ | + = -`). Fixed for the
  sandbox's life.
- `tags`: up to 16 string pairs, replaceable later with `PATCH /sandboxes/{id}`.

It is ready in about two minutes (`sandbox.ready` webhook, or poll `GET /sandboxes/{id}`).

Refusals take no money: `402 spend_cap_reached` (a cap), `402 insufficient_credits`, `409 limit`
(live-sandbox limit), `503 at_capacity` (we are full: try again later).

---

## 3. List, read, change, delete

```bash
GET    /sandboxes?end_user_id=cust_8341            # one user's sandboxes
GET    /sandboxes?tag.team=acme&state=asleep       # by tag and state (default: live ones; state=all)
GET    /sandboxes/{id}                             # state, billing, awake hours, spent so far
PATCH  /sandboxes/{id}      {"tags": {...}}
POST   /sandboxes/{id}/wake        POST /sandboxes/{id}/sleep
DELETE /sandboxes/{id}
GET    /usage/sandboxes?month=2026-11              # your statement, one row per end user
```

Run commands, read and write files, open preview links and mint OpenAI-compatible keys with the
same routes as any sandbox: `/pods/v1/pods/{id}/exec`, `/files`, `/ports`, `/keys`.

---

## 4. Caps: what happens at the limit

- The next awake hour that would pass a cap is not charged: the sandbox goes **on hold** and sleeps
  (`sandbox.cap_reached`, `billing.hold_reason` = `cap_platform`, `cap_end_user` or
  `insufficient_credits`). It will not wake while on hold.
- If a day of **disk** cannot be paid, the sandbox is deleted after **7 days** unless it is paid by
  then (`billing.deletes_at`, and `sandbox.deleting` just before).
- Raise the cap or add credits and the hold lifts by itself on the next wake.

---

## 5. Webhooks

Use the pod webhooks (`POST /pods/v1/webhooks` with your https URL; signed `t=...,v1=...` HMAC). Every
sandbox event carries `data.end_user_id`.

| Event | When |
|-------|------|
| `sandbox.created` | the create went through |
| `sandbox.ready` | the sandbox is up and usable |
| `sandbox.awake` / `sandbox.asleep` | woke / went to sleep (`data.reason`: idle, api, unpaid...) |
| `sandbox.cap_reached` | put on hold (`data.reason`, `data.deletes_at`) |
| `sandbox.deleting` / `sandbox.deleted` | being deleted / gone |
| `sandbox.usage` | once a day: yesterday's `awake_hours`, `disk_days`, `total_usd` |

Missed one? `GET /pods/v1/events?after=<seq>`.

---

## 6. Embed the terminal in your app

Your server asks for a short-lived link for one sandbox and gives it to that user's browser:

```bash
curl -X POST https://compute.x402layer.cc/pods/v1/sandboxes/{id}/embed-token \
  -H "X-API-Key: $SGL_API_KEY" -H "content-type: application/json" -d '{"ttl_seconds": 900}'
# -> { "embed_url": "https://compute.x402layer.cc/pods/embed/{id}/terminal#token=sbx_emb_...",
#      "token": "sbx_emb_...", "ticket_url": ".../pods/embed/{id}/ticket", "expires_at": "..." }
```

```html
<iframe src="EMBED_URL" style="width:100%;height:480px;border:0" allow="clipboard-read; clipboard-write"></iframe>
```

- Only your `embed_origins` may frame it. The page has no branding.
- The token is for that one sandbox, terminal only, 60 s to 1 h (default 15 min). It sits in the URL
  fragment, so it never reaches a server log.
- Revoke every link for a sandbox: `POST /sandboxes/{id}/embed-token/revoke`.
- Your own terminal UI instead: `POST ticket_url` with `Authorization: Bearer <token>` (CORS open to
  your `embed_origins`) returns `{ws_url}`: text frame `{"cols":..,"rows":..}` resizes, binary
  frames are the terminal's input and output.

---

## SDK snippets

TypeScript:

```ts
const API = "https://compute.x402layer.cc/pods/v1";
const h = { "X-API-Key": process.env.SGL_API_KEY!, "content-type": "application/json" };

export async function sandboxFor(userId: string) {
  const list = await (await fetch(`${API}/sandboxes?end_user_id=${encodeURIComponent(userId)}`, { headers: h })).json();
  if (list.sandboxes?.length) return list.sandboxes[0];
  const r = await fetch(`${API}/sandboxes`, {
    method: "POST",
    headers: { ...h, "Idempotency-Key": crypto.randomUUID() },  // reuse the same key if you retry this request
    body: JSON.stringify({ harness: "opencode", ai_mode: "managed", end_user_id: userId }),
  });
  if (!r.ok) throw new Error(`${r.status} ${JSON.stringify(await r.json())}`);
  return (await r.json()).sandbox;
}

export async function terminalUrl(sandboxId: string) {
  const r = await fetch(`${API}/sandboxes/${sandboxId}/embed-token`, { method: "POST", headers: h, body: "{}" });
  return (await r.json()).embed_url as string;
}
```

Python:

```python
import os, uuid, requests
API = "https://compute.x402layer.cc/pods/v1"
H = {"X-API-Key": os.environ["SGL_API_KEY"]}

def sandbox_for(user_id: str) -> dict:
    found = requests.get(f"{API}/sandboxes", params={"end_user_id": user_id}, headers=H).json()["sandboxes"]
    if found:
        return found[0]
    r = requests.post(f"{API}/sandboxes", headers={**H, "Idempotency-Key": str(uuid.uuid4())},
                      json={"harness": "opencode", "ai_mode": "managed", "end_user_id": user_id})
    r.raise_for_status()
    return r.json()["sandbox"]

def statement(month: str) -> dict:
    return requests.get(f"{API}/usage/sandboxes", params={"month": month}, headers=H).json()
```

(Use a new `Idempotency-Key` for each new sandbox and the same one when you retry that request.)
