# ADR-0002: Repository foundation bootstrap

- **Status:** Accepted
- **Date:** 2026-05-30
- **Authors:** IBEX Harness team

## Context

Documentation and AI guardrails exist, but the repo lacked hygiene files, CI enforcement, ADR directory, and stable top-level paths before implementation.

## Decision

1. **Hygiene:** Add `.gitignore`, `.editorconfig`, `.gitattributes`; license set to **MIT** ([LICENSE](../../LICENSE)).
2. **CI (PR-only, fast):** Structural markdown lint, gitleaks, forbidden-file checks, repo layout guard. No language build/test until services exist.
3. **Markdown policy:** `markdownlint-cli2` tuned via `.markdownlint-cli2.jsonc` — style rules (MD013, MD022, MD024, MD029, MD032, MD056, MD060, etc.) disabled for existing reference docs; structural rules (fences MD031/MD040, link integrity) remain enabled. Tighten rules incrementally as docs are normalized.
4. **Dependabot:** Enable `github-actions` weekly updates; enable root `gomod` when `go.mod` exists at repo root ([ADR-0008](ADR-0008-security-ci-gates.md)). Enable `pip` / `npm` when memory/dashboard manifests exist (see `.github/dependabot.yml` comments).
5. **Branch:** Rename default branch `master` → `main` to match [DEVELOPMENT_GUIDE.md](../DEVELOPMENT_GUIDE.md) and [DEPLOYMENT.md](../DEPLOYMENT.md).
6. **Scaffold dirs:** Create `services/`, `packages/`, `infra/` with README stubs only (no service code in this ADR).
7. **Templates:** PR template aligned with DEVELOPMENT_GUIDE §7.2; bug/feature/security issue templates.

## Consequences

### Positive

- Implementation PRs cannot accidentally commit `.env` or break doc structure.
- Stable paths for AI agents and humans.

### Negative

- `main` rename requires one-time remote/default-branch update on GitHub.
- License chosen as MIT (2026); update copyright holder name if the legal entity changes.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Full CI with Go/Python/TS now | No code; would be red or meaningless |
| Renovate instead of Dependabot | Dependabot is native to GitHub; sufficient for now |
| Keep `master` | Docs already standardize on `main` |

## License

MIT — see [LICENSE](../../LICENSE) at repository root (added after initial bootstrap).

## References

- [FILE_STRUCTURE.md](../FILE_STRUCTURE.md)
- [DEPLOYMENT.md](../DEPLOYMENT.md) §5
- [DEPENDENCIES.md](../DEPENDENCIES.md)
