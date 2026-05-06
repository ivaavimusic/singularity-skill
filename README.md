# Singularity Skill

Portable full-platform agent skill for x402 Studio and Singularity Layer.

Current release: `v1.11.1`

## Install

```bash
npx skills add https://github.com/ivaavimusic/singularity-skill --skill singularity
```

## Repository Layout

- `singularity/` — installable skills.sh package

## Notes

- This is the public portable-skill distribution repo.
- The OpenClaw-specific sibling remains `x402-layer`.
- This release keeps the webhook hardening guidance, preserves optional OpenWallet / OWS support, and adds direct fundraiser campaign management through owner-linked dashboard API keys alongside the PAT-backed MCP path.
- MCP remains the PAT-backed control plane for owner-scoped management and payment tooling, while direct worker routes can use an existing owner-linked `X-API-Key`.
