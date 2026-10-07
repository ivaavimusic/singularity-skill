# Singularity Skills

Portable skills.sh distribution for x402 Studio and the Singularity Layer. Two skills:

- **`singularity`** (`v1.11.1`) — full-platform marketplace & payments: pay/consume APIs in USDC, deploy monetized endpoints, credits, webhooks, marketplace listings, ERC-8004 agent registration, AWAL/OWS, multi-chain.
- **`x402-compute`** (`v1.31.0`) — the **Singularity Cloud Network**: rent GPU/VPS instances (SGL Machines), run confidential OpenAI-compatible inference and release-gated text/image/audio/video embeddings (SGL Grid), operate a node to earn USDC + SGL, deploy Agent Pods, buy generated **fine-tuning datasets** over x402, and back up / migrate agents with **Agent Vault**.

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

## Notes

- This is the public portable-skill distribution repo.
- The OpenClaw-specific sibling of `singularity` remains `x402-layer`.
- `x402-compute` here mirrors the canonical source (served live at `api.x402layer.cc/skill/x402-compute`); keep them in sync.
- This release adds the release-gated EmbeddingGemma 2 contract: ordered text/image/audio/video inputs, 768/512/256/128 normalized vectors, a request-building script, exact limits/errors, and Local/Grid routing guidance. It does not enable production traffic.
- MCP remains the PAT-backed control plane for owner-scoped management and payment tooling, while direct worker routes can use an existing owner-linked `X-API-Key`.
