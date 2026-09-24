# Security CI gates — required controls and evidence boundary

Reference for the DevSecOps hardening work associated with PR #18 and [ADR-0008](adr/ADR-0008-security-ci-gates.md). The inventory below describes required controls; it is not, by itself, evidence that every workflow or branch-protection check is enabled in the current baseline.

## Referenced controls (verify before relying on them)

| Area | Paths |
|------|--------|
| Workflows | `.github/workflows/ci.yml`, `codeql.yml`, `semgrep.yml`, `scorecard.yml`, `sbom.yml` |
| Config | `.github/dependabot.yml`, `.github/branch-protection-main.json`, `.semgrep/rules/ibex-security.yml`, `.semgrepignore`, `.hadolint.yaml` |
| Docs / ADR | `CONTRIBUTING.md`, `SECURITY.md` §12.2, `DEPENDENCIES.md` §9, `TOOLCHAIN.md`, `ADR-0008`, `ADR-0003`, `ADR-0002` |
| Agent guidance | `AGENTS.md`, `CLAUDE.md` |

## Severity thresholds

| Scanner | Merge gate? | Fail threshold |
|---------|-------------|----------------|
| Trivy (fs) | Yes | CRITICAL, HIGH (`ignore-unfixed: true`) |
| OSV Scanner | Yes | Unfixed vulns in `pnpm-lock.yaml` (JS). Go enforced by `govulncheck` — see ADR-0008 |
| Semgrep | Yes | `.semgrep/rules/` only (`--error`); community packs → SARIF only |
| Grype (SBOM) | No | `--fail-on critical`; table/JSON artifacts only (not Code Scanning SARIF) |
| golangci-lint | Yes | Lint errors on auth + proxy |
| bandit / hadolint | Yes | Findings per tool defaults |

## Required status checks (branch protection)

`repo-guards`, `markdownlint`, `gitleaks`, `CodeQL`, `trivy`, `osv-scan`, `semgrep`, `golangci-lint`, `bandit`, `hadolint` — apply after merge:

```bash
gh api --method PUT repos/Rick1330/ibex-harness/branches/main/protection \
  --input .github/branch-protection-main.json
```

## Toolchain

- `go.mod` **Go 1.25.13** with `go-version-file: go.mod` in CI.
- `golang.org/x/crypto` **v0.54.0+** (direct require in `packages/crypto`; Argon2id per ADR-0010).
- **Go vulnerability gates:** `govulncheck` (reachable stdlib/module vulns). OSV scans JS lockfiles only — `GO-2026-5932` is a module-level `openpgp` advisory that OSV cannot mark unexecuted when only `argon2` is imported (ADR-0008).
- Docker builder images: `golang:1.26-alpine3.22` (≥ `go.mod` minimum; no `GOTOOLCHAIN=auto` needed).

## Local verification

```bash
cd packages/proto && buf generate && cd ../..
go test ./services/auth/... ./services/proxy/... ./packages/proto/...
golangci-lint run ./services/auth/... ./services/proxy/...
semgrep --config .semgrep/rules/ --error services/ packages/
trivy fs --severity CRITICAL,HIGH --ignore-unfixed .
osv-scanner --lockfile pnpm-lock.yaml
govulncheck ./packages/... ./services/auth/... ./services/proxy/...
```

## Repo admin (one-time)

1. Revoke any PAT exposed in chat; CI uses `GITHUB_TOKEN` only.
2. Disable CodeQL **Default** setup; keep `.github/workflows/codeql.yml`.


## Operator-web gates

The canonical product is `services/operator-web`; `web/` remains public docs and `services/dashboard/` remains a temporary compatibility shell. Before operator-web staging promotion, CI must publish evidence for:

- OpenAPI snapshot diff, generated TypeScript client freshness, runtime DTO validation, and versioned SSE envelope validation;
- four-role/two-tenant contract and authenticated browser journeys, including tenant-negative authorization;
- CSRF, exact credentialed CORS, secure cookie settings, security headers, hostile-content sanitization, and `Cache-Control: no-store`/cache-isolation checks;
- SSE resume/deduplication/slow-client/drain behavior and page/query/SSE performance budgets;
- accessibility (axe plus keyboard/screen-reader states), visual baselines, immutable artifact identity, and rollback evidence.

Do not mark a route, hostname, deployment workflow, operator-web workload, or shell retirement as implemented without a linked artifact or environment record.
