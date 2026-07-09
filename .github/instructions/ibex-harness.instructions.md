# IBEX Harness — Copilot repository instructions

Read before reviewing or suggesting code changes:

- [.cursorrules](../../.cursorrules)
- [AGENTS.md](../../AGENTS.md)
- [web/engineering/SECURITY.md](../../web/engineering/SECURITY.md)
- [web/engineering/FILE_STRUCTURE.md](../../web/engineering/FILE_STRUCTURE.md)

## Governance

- **Never** commit or push directly to `main`. All changes use a feature branch and pull request.
- Required CI checks before merge: `repo-guards`, `markdownlint`, `gitleaks`.
- Copilot PR review is **advisory**; it does not replace CI or human/self-review.

## Non-negotiable invariants

- **Tenant isolation:** every data path must scope by `org_id`; no cross-tenant access.
- **Secrets:** never commit credentials, tokens, or `.env` files with real values.
- **No fake implementations:** do not add placeholder logic in core service paths (auth, proxy, memory, tenant isolation).
- **Docs are source of truth:** do not invent APIs, tables, or env vars not defined under `docs/`.
- **Layout:** follow `web/engineering/FILE_STRUCTURE.md`; do not add new top-level directories without an ADR.

## Review focus

- Security and multi-tenancy implications
- Alignment with documented contracts (`web/engineering/API_DOCUMENTATION.md`, `packages/proto/`)
- Repo layout and CI guard compliance
- Clarity of tests and docs when behavior changes
