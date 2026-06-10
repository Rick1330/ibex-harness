# CI Job Audit — Pre-Phase 2 Verification

**Date:** 2026-06-10  
**Purpose:** Document what each CI job validates, false-positive risks, and mitigation status.

---

## Required checks (branch protection)

| Context | Workflow job | Validates | False-positive risk | Mitigation |
|---------|--------------|-----------|---------------------|------------|
| `repo-guards` | `repo-guards` | Layout, secrets, large files | Low | — |
| `markdownlint` | `markdown` | Markdown style | Low | — |
| `gitleaks` | `secrets` | Secret scan | Low | — |
| `CodeQL` | `codeql.yml` | Static security analysis | Low | — |
| `trivy` | `trivy` | FS vulnerability scan | Low | — |
| `osv-scan / osv-scan` | `osv-scan` | Dependency CVEs | Low | — |
| `semgrep` | `semgrep.yml` | SAST rules | Low | — |
| `golangci-lint` | `golangci-lint` | Go lint (packages + auth + proxy) | Medium: weaker than cursor rules | Incremental linter enablement deferred |
| `security-integration` | `security-integration` | M1.5.1 `TestSecurity_*` matrix | **Was critical:** `-run` with 0 matches exits 0 | Pre-flight `-list` count ≥ 28 |
| `go-race` | `go-race` | Unit tests under `-race` | Medium: no integration + race | Scheduled integration+race deferred |
| `go-services (auth)` | `go-services` matrix | Unit tests + gofmt + build | Was informational | Promoted; `-count=1` |
| `go-services (proxy)` | `go-services` matrix | Unit tests + gofmt + build | Was informational | Promoted; `-count=1` |
| `proxy-auth-smoke` | `proxy-auth-smoke` | Full proxy unit + integration | Was informational | Promoted; `-count=1` |
| `bandit` | `bandit` | Python SAST | **High until memory service:** exits 0 if missing | Not required until `services/memory` exists |
| `hadolint` | `hadolint` | Dockerfile lint | Low (exits 0 if no Dockerfiles) | — |

## Informational checks (not merge-blocking)

| Job | Notes |
|-----|-------|
| `coverage` | Codecov upload (Go unit); not required until baseline established; no harden-runner (Codecov CLI needs GPG key fetch + execute bit) |
| `auth-validate-smoke` | Auth integration; `-count=1` |
| `proxy-agent-verify-smoke` | SEC-2/SEC-3 subset; explicit `-run` + count guard |
| `db-migrate-smoke` | Migration idempotency |
| `proto-contract` | Buf contract tests |
| `buf-lint` | Skips `buf breaking` without main baseline |
| `compose-validate` | Compose config syntax |
| `dependency-review` | PR dependency policy |
| `sbom` | SBOM generation |
| CodeScene | Advisory code health |

## Known deferrals

- `golangci-lint` does not yet enable gocyclo/funlen/gosec from cursor rules
- `infra/` Go packages not in golangci scope
- Integration test coverage not in Codecov yet (Postgres required)
- Python (`bandit`) and TypeScript coverage flags when services land

## Manual ops

After promoting checks, apply [`.github/branch-protection-main.json`](../../../.github/branch-protection-main.json) on GitHub repository settings.
