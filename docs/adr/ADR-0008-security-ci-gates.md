# ADR-0008: Security scanning and CI quality gates

- **Status:** Accepted
- **Date:** 2026-06-02
- **Authors:** IBEX Harness team

## Context

[docs/SECURITY.md](../SECURITY.md) §12.2 and [docs/DEPENDENCIES.md](../DEPENDENCIES.md) §9 listed recommended scanners that were not wired in CI. [ADR-0003](ADR-0003-branch-protection-and-merge-policy.md) required only `repo-guards`, `markdownlint`, and `gitleaks`. `golangci-lint` ran with `continue-on-error: true`, providing no merge enforcement.

The repo has a single root `go.mod`, Go services `auth` and `proxy`, two Dockerfiles, and no Python/TypeScript application code yet.

## Decision

### Workflows added

| Workflow | Purpose | PR required check |
|----------|---------|-------------------|
| `.github/workflows/codeql.yml` | CodeQL (`go` now; python/javascript when app code exists) | `CodeQL` |
| `.github/workflows/semgrep.yml` | IBEX custom rules (hard gate) + community rules (SARIF, non-blocking) | `semgrep` |
| `.github/workflows/scorecard.yml` | OSSF supply-chain score | No |
| `.github/workflows/sbom.yml` | Syft SBOM + Grype scan (CRITICAL); reports as workflow artifacts only (no SARIF upload—Grype SBOM SARIF lacks GitHub `artifactLocation`) | No |

### CI jobs added or changed (`.github/workflows/ci.yml`)

| Job | Failure threshold |
|-----|-------------------|
| `trivy` | CRITICAL/HIGH filesystem CVEs; `ignore-unfixed: true` |
| `osv-scan` | CRITICAL/HIGH via OSV reusable workflow |
| `hadolint` | ≥ warning (`.hadolint.yaml`) |
| `bandit` | HIGH+HIGH when `services/memory` exists; skip (success) until then |
| `golangci-lint` | Any lint issue; single job for auth+proxy; no `continue-on-error` |

Weekly `schedule` on CI runs **only** `osv-scan` (other jobs use `if: github.event_name != 'schedule'`).

CI uses `go-version-file: go.mod` so the runner Go version tracks `go.mod` (currently **1.25.11**; `golang.org/x/crypto` ≥ v0.52.0; golangci-lint **v2.4+** for Go 1.25).

### CodeQL default vs advanced

GitHub **Default** CodeQL setup conflicts with the advanced `.github/workflows/codeql.yml` (SARIF rejected). **Repo admin must disable Default setup** (Settings → Code security → Code scanning → CodeQL → Advanced) before the `CodeQL` check is reliable.

### Dependabot

- Active: `github-actions`, `gomod` at `/`
- Deferred (documented in `.github/dependabot.yml`): `pip` (`/services/memory`), `npm` (`/services/dashboard`)

### Branch protection

[`.github/branch-protection-main.json`](../../.github/branch-protection-main.json) adds: `CodeQL`, `trivy`, `osv-scan`, `semgrep`, `golangci-lint`, `bandit`, `hadolint`.

Apply after the governance PR registers check names:

```bash
gh api --method PUT \
  repos/Rick1330/ibex-harness/branches/main/protection \
  --input .github/branch-protection-main.json
```

### AI agent enforcement

- Custom Semgrep rules encode `.cursorrules` invariants
- [prompts/20-security-ci-audit.txt](../../prompts/20-security-ci-audit.txt) for CI/security config reviews
- `.cursorrules` §9.5 CI tooling invariants

## Consequences

### Positive

- Unified dependency CVE coverage (OSV) and container/filesystem scanning (Trivy)
- IBEX-specific invariants enforced mechanically on every PR
- Supply-chain visibility (Scorecard, SBOM) without blocking solo merge velocity on informational jobs

### Negative

- First PR may fail until CVEs/lint/hadolint findings are fixed
- Branch protection cannot include new checks until GitHub has seen them on a PR
- CodeQL requires one-time disable of GitHub Default setup

## References

- [CONTRIBUTING.md](../../CONTRIBUTING.md)
- [ADR-0003](ADR-0003-branch-protection-and-merge-policy.md)
- [docs/SECURITY.md](../SECURITY.md) §12.2
