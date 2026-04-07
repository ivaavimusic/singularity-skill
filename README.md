# Singularity Skill

Portable full-platform agent skill for x402 Studio and Singularity Layer.

Current release: `v1.10.6`

## Install

```bash
npx skills add https://github.com/ivaavimusic/singularity-skill --skill singularity
```

## Repository Layout

- `singularity/` — installable skills.sh package

## Notes

- This is the public portable-skill distribution repo.
- The OpenClaw-specific sibling remains `x402-layer`.
- This release adds explicit Studio seller webhook signing guidance, keeps credentialed actions scoped to the exact runbook that needs them, and preserves optional OpenWallet / OWS support plus the existing AgentKit, XMTP, and PAT-backed MCP guidance.
- MCP remains the PAT-backed control plane for owner-scoped management and payment tooling.
