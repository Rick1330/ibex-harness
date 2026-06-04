# Milestone 1.1.5 — Execution Prompt: Permission Bitmap Contract

Copy this prompt into your AI tool (Cursor, Codex, etc.) to implement the milestone. Do not add agent attribution to commits or PRs.

---

You are acting as **Principal Engineer + Security Owner** for IBEX Harness.

## Mission

Implement **Milestone 1.1.5: Permission Bitmap Contract and ADR** as defined in [../phase-1-core-platform/milestones/1.1.5-permission-bitmap-contract-and-adr.md](../phase-1-core-platform/milestones/1.1.5-permission-bitmap-contract-and-adr.md).

## You MUST read first

- [AGENTS.md](../../../AGENTS.md)
- [.cursorrules](../../../.cursorrules)
- [docs/adr/ADR-0006-auth-proto-contract.md](../../adr/ADR-0006-auth-proto-contract.md)
- [docs/ARCHITECTURE.md](../../ARCHITECTURE.md) — permission bitmap
- [docs/SECURITY.md](../../SECURITY.md) §4.3
- [docs/roadmap/phase-1-core-platform/decisions.md](../phase-1-core-platform/decisions.md)
- [prompts/00-invariants.txt](../../../prompts/00-invariants.txt)

## Non-negotiable constraints

- **Do not renumber** `ValidateTokenResponse` proto fields (ADR-0006 locked)
- **ADR-0009** for bitmap (ADR-0007 is token validation; ADR-0008 is CI gates)
- **PR template** — fill all sections from `.github/pull_request_template.md`
- **PR-only** to `main`; no agent attribution

## Branch

`chore/m1-1-5-permission-bitmap`

## Deliverables

1. `packages/permissions` with constants, predefined sets, `Has` / `HasAny` / `RequiresMFA`
2. [ADR-0009](../../adr/ADR-0009-permission-bitmap.md)
3. Unit tests (overlap, subsets, reserved bits, MFA)
4. Update `SECURITY.md`, `decisions.md`, phase README

## Verification

```bash
go test ./packages/permissions/...
make repo-guards
```

---

*Reference: [roadmap README](../README.md)*
