# Milestone 1.1.2 — Execution Prompt: Auth Protobuf and Codegen

Copy this prompt into your AI tool (Cursor, Codex, etc.) to implement the milestone. Do not add agent attribution to commits or PRs.

---

You are acting as **Principal Engineer + Contract Owner** for IBEX Harness.

## Mission

Implement **Milestone 1.1.2: Auth Protobuf and Codegen** as defined in [../phase-1-core-platform/milestones/1.1.2-auth-proto-and-codegen.md](../phase-1-core-platform/milestones/1.1.2-auth-proto-and-codegen.md).

## You MUST read first

- [AGENTS.md](../../../AGENTS.md)
- [.cursorrules](../../../.cursorrules)
- [docs/adr/ADR-0004-protobuf-and-codegen-policy.md](../../adr/ADR-0004-protobuf-and-codegen-policy.md) — gen/ not committed; buf lint/breaking
- [docs/adr/ADR-0005-postgres-migration-strategy.md](../../adr/ADR-0005-postgres-migration-strategy.md) — schema context for later 1.1.3
- [packages/proto/proto/ibex/context/v1/context.proto](../../../packages/proto/proto/ibex/context/v1/context.proto) — naming and `go_package` pattern
- [packages/proto/README.md](../../../packages/proto/README.md)
- [docs/ARCHITECTURE.md](../../ARCHITECTURE.md) — auth validation pipeline (gRPC)
- [docs/API_DOCUMENTATION.md](../../API_DOCUMENTATION.md) — Bearer token semantics
- [docs/roadmap/phase-1-core-platform/milestones/1.1.3-auth-token-validation.md](../phase-1-core-platform/milestones/1.1.3-auth-token-validation.md) — consumer of this contract
- [docs/roadmap/phase-1-core-platform/milestones/1.2.1-proxy-auth-client.md](../phase-1-core-platform/milestones/1.2.1-proxy-auth-client.md) — proxy client consumer
- [prompts/00-invariants.txt](../../../prompts/00-invariants.txt)

If any file is inaccessible, STOP and ask for it.

## Non-negotiable constraints

- **Contracts only** — no auth service implementation, no Postgres queries, no proxy middleware in this PR.
- **No committed `packages/proto/gen/`** — per ADR-0004; CI must not require generated stubs.
- **PR-only workflow** to `main`; required CI: `repo-guards`, `markdownlint`, `gitleaks`.
- **Package:** `ibex.auth.v1`; minimal v1 surface: `ValidateToken` RPC + request/response messages needed by 1.1.3 and 1.2.1.
- **Never put raw tokens in logs** — proto field names are fine; implementation milestones handle redaction.
- **No agent attribution** in commits or PR description.

## Branch

`chore/m1-1-2-auth-proto-codegen`

## PR title (example)

`chore(proto): auth protobuf and codegen (m1.1.2)`

## Deliverables

1. **ADR-0006** — auth proto layout, RPC naming, error/status model, `go_package` path, relationship to ADR-0004.
2. **`packages/proto/proto/ibex/auth/v1/auth.proto`** — `AuthService` with `ValidateToken`.
3. **Messages (minimum):**
   - Request: opaque bearer token string (field name e.g. `token` or `access_token`; document that service hashes internally).
   - Response (success): `org_id`, `permissions` (int64 bitmap), optional `agent_id`, `user_id`, `token_id`, `expires_at`.
   - Response (failure): use gRPC status codes + optional structured error details (document in ADR-0006); do not invent a parallel HTTP envelope in proto.
4. **`packages/proto/README.md`** — table row for `ibex.auth.v1`; local `buf generate` steps.
5. **`buf.gen.yaml`** — confirm Go output under `gen/go` with `paths=source_relative` (already configured; adjust only if needed).
6. **Optional:** `make proto-gen` in `dev-tool.sh` + `Makefile` (runs `buf generate` in `packages/proto`; local only).
7. **CI** — existing `buf-lint` job must pass with new package; `buf breaking` against `main` after first merge of auth proto.

## ValidateToken contract hints (align with architecture)

- Input: full bearer token as sent in `Authorization: Bearer ...` (e.g. `ibex_pat_...`).
- Output on success: org context for `SET LOCAL app.current_org_id` in 1.1.3; permission bitmap for proxy enforcement in 1.2.1.
- Revoked/expired/invalid token → `Unauthenticated` or `PermissionDenied` per ADR-0006 (document choice).
- Do not add JWT issuance RPCs in this milestone.

## Definition of done

- `buf lint` passes locally and in CI.
- `buf breaking` passes against `main` (after this PR establishes baseline, or same PR if additive-only).
- Local `buf generate` produces importable Go stubs under `packages/proto/gen/go/ibex/auth/v1/` (not committed).
- `go_package` matches root module: `github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1;authv1` (or consistent with context package).
- No service code changes beyond docs/Makefile optional target.
- Required CI checks pass.

## Output format

1. Short implementation plan (files + order).
2. Implement via PR-sized commits.
3. PR description using repo template: What/Why, How, Testing, Security, Docs.
4. Verification commands with expected results.
5. Risks/assumptions.

## Verification commands (expected)

```bash
cd packages/proto
buf lint
buf breaking --against "https://github.com/Rick1330/ibex-harness.git#branch=main,subdir=packages/proto"
buf generate
ls gen/go/ibex/auth/v1/    # files exist locally; must not appear in git status

make repo-guards
make lint-docs
make proto-lint            # from repo root, if wired
```

## After merge

Update [docs/roadmap/CURRENT_STATE.md](../CURRENT_STATE.md): SHA, mark 1.1.2 complete, next milestone 1.1.3.

---

*Reference: [roadmap README](../README.md)*
