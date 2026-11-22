# Singularity Skills

Portable skills.sh distribution for x402 Studio and the Singularity Layer. Two skills:

- **`singularity`** (`v1.14.0`): full-platform marketplace & payments: pay/consume APIs in USDC, deploy monetized endpoints, credits, webhooks, marketplace listings, the paid **flow planner** (describe a job, get a priced flow of x402 services for $0.02), ERC-8004 agent registration, AWAL/OWS, multi-chain.
- **`x402-compute`** (`v1.41.0`): the **Singularity Cloud Network**: rent GPU/VPS instances (SGL Machines), run confidential inference (OpenAI-compatible and Anthropic-compatible, including Claude Code), multimodal embeddings and release-gated client-sealed speech-to-text (SGL Grid), operate a node to earn USDC + SGL, deploy Agent Pods (ClawPod, HermPod or Pi; run commands, edit files and open ports through the Sandbox API), use a **Coding sandbox** from your own terminal or any OpenAI client, give **your own users** coding sandboxes (pay as you go, per-user tags and caps, embeddable terminal), buy generated **fine-tuning datasets** and **train a model on them (Training Lab)** over x402, and back up / migrate agents with **Agent Vault**.

## Install

```bash
# Marketplace & payments
npx skills add https://github.com/ivaavimusic/singularity-skill --skill singularity

# Cloud Network compute, inference & run-a-node
npx skills add https://github.com/ivaavimusic/singularity-skill --skill x402-compute
```

`x402-compute` is also available as a hosted one-liner:

```bash
curl -fsSL https://api.x402layer.cc/skill/x402-compute/install | bash
```

## Repository Layout

- `singularity/` — marketplace/payments skills.sh package
- `x402-compute/` — Cloud Network (compute/inference/node) skills.sh package

## Tests

Repo-only (not part of either installed skill):

```bash
python3 -m unittest discover -s tests/singularity
python3 -m unittest discover -s tests/x402-compute
```

## Changelog

- **singularity 1.14.0 / x402-compute 1.39.0 (x402 v2):** the paying scripts read the v2 `PAYMENT-REQUIRED` header first and pay with `PAYMENT-SIGNATURE`; without it they pay v1 `X-Payment` exactly as before (`X402_WIRE=v1` forces v1). Base and Solana (and Robinhood / Arc in x402-compute). Shared helper `scripts/x402_wire.py` (standard library only) is byte-identical to the official @x402/core encoding. After a payment is sent, a timeout, 202 or 5xx is reported as `pending: true`, never a reason to sign again. `consume_product.py` now buys from the live `api.x402layer.cc/p/<slug>` route (Base or Solana) instead of sending a raw-JSON header to the retired `/storage/product/` path.

## Notes

- This is the public portable-skill distribution repo.
- The OpenClaw-specific sibling of `singularity` remains `x402-layer`.
- `x402-compute` here mirrors the canonical source (served live at `api.x402layer.cc/skill/x402-compute`); keep them in sync.
- This candidate adds the default-off `transcription-v1` contract: Local/Grid routing, metadata-only reservation, client-sealed JSON submission, exact PCM limits, per-audio-second pricing, privacy/retention guidance, and a validation/SDK helper. It does not enable production traffic or claim that `whisper-1` is publicly available.
- MCP remains the PAT-backed control plane for owner-scoped management and payment tooling, while direct worker routes can use an existing owner-linked `X-API-Key`.
