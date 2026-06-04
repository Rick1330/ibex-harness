# Milestone 1.1.6 — Execution Prompt: Argon2id Parameters and Crypto Policy ADR

Copy this prompt into your AI tool (Cursor, Codex, etc.) to implement the milestone. Do not add agent attribution to commits or PRs.

---

You are acting as **Principal Engineer + Security Owner** for IBEX Harness.

## Mission

Implement **Milestone 1.1.6: Argon2id Parameters and Crypto Policy ADR** as defined in [../phase-1-core-platform/milestones/1.1.6-argon2id-parameters-and-crypto-policy-adr.md](../phase-1-core-platform/milestones/1.1.6-argon2id-parameters-and-crypto-policy-adr.md).

## You MUST read first

- [AGENTS.md](../../../AGENTS.md) — §5.4 approved cryptography
- [.cursorrules](../../../.cursorrules) — §1.6.2 post-implementation testing
- [docs/adr/ADR-0007-auth-token-validation.md](../../adr/ADR-0007-auth-token-validation.md)
- [docs/adr/ADR-0008-security-ci-gates.md](../../adr/ADR-0008-security-ci-gates.md) — **not** crypto policy (do not reuse number)
- [docs/adr/ADR-0010-cryptography-policy.md](../../adr/ADR-0010-cryptography-policy.md) (create)
- [docs/SECURITY.md](../../SECURITY.md) §4.2
- [docs/TESTING_STRATEGY.md](../../TESTING_STRATEGY.md) §6
- [services/auth/internal/token/hash.go](../../../services/auth/internal/token/hash.go)
- [prompts/00-invariants.txt](../../../prompts/00-invariants.txt)

## Non-negotiable constraints

- **ADR-0010** for crypto policy — ADR-0008 is CI gates only
- **`packages/crypto`** only — no root `internal/crypto` (repo-guards)
- **No** direct `golang.org/x/crypto/argon2` outside `packages/crypto`
- **Production defaults:** `m=65536`, `t=3`, `p=4`, salt 16 B, key 32 B
- **PHC format** embedded in hash; verify reads params from PHC string
- **PR body** from `ibex-harness-workspace/pr-bodies/` — never commit under `.github/`
- **PR-only** to `main`; no agent attribution

## Branch

`chore/m1-1-6-crypto-policy`

## PR title

`chore(security): Argon2id parameters and crypto policy ADR (m1.1.6)`

## Deliverables

1. [ADR-0010](../../adr/ADR-0010-cryptography-policy.md) + amend ADR-0007 §5 cross-ref
2. `packages/crypto` — HashSecret/VerifySecret, token/password aliases, random, ConstantTimeEqual
3. Migrate `services/auth/internal/token` + `infra/testing/testutil/hash.go`
4. Update SECURITY.md, ARCHITECTURE.md, ENVIRONMENT_VARIABLES.md, decisions.md, phase README

## Verification

```bash
go test ./packages/crypto/...
go test ./services/auth/...
go test -tags=integration ./services/auth/...
make repo-guards
golangci-lint run ./packages/crypto/... ./services/auth/...
```

---

*Reference: [roadmap README](../README.md)*
