# Security CI gates — deliverables (PR #18)

Reference for the DevSecOps hardening work on branch `chore/security-ci-gates`. See [ADR-0008](adr/ADR-0008-security-ci-gates.md).

## Files added or materially changed

| Area | Paths |
|------|--------|
| Workflows | `.github/workflows/ci.yml`, `codeql.yml`, `semgrep.yml`, `scorecard.yml`, `sbom.yml` |
| Config | `.github/dependabot.yml`, `.github/branch-protection-main.json`, `.semgrep/rules/ibex-security.yml`, `.semgrepignore`, `.hadolint.yaml` |
| Docs / ADR | `CONTRIBUTING.md`, `SECURITY.md` §12.2, `DEPENDENCIES.md` §9, `TOOLCHAIN.md`, `ADR-0008`, `ADR-0003`, `ADR-0002` |
| Prompts | `prompts/20-security-ci-audit.txt`, `.cursorrules` §9.5 |

## Severity thresholds

| Scanner | Merge gate? | Fail threshold |
|---------|-------------|----------------|
| Trivy (fs) | Yes | CRITICAL, HIGH (`ignore-unfixed: true`) |
| OSV Scanner | Yes | Any unfixed vuln in lockfiles (`fail-on-vuln`) |
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

- `go.mod` **Go 1.25.11** with `go-version-file: go.mod` in CI.
- `golang.org/x/crypto` **v0.52.0+** for critical `x/crypto` advisories (requires Go ≥ 1.25).
- Docker builder images: `golang:1.25-alpine3.20`.

## Local verification

```bash
cd packages/proto && buf generate && cd ../..
go test ./services/auth/... ./services/proxy/... ./packages/proto/...
golangci-lint run ./services/auth/... ./services/proxy/...
semgrep --config .semgrep/rules/ --error services/ packages/
trivy fs --severity CRITICAL,HIGH --ignore-unfixed .
osv-scanner --recursive .
```

## Repo admin (one-time)

1. Revoke any PAT exposed in chat; CI uses `GITHUB_TOKEN` only.
2. Disable CodeQL **Default** setup; keep `.github/workflows/codeql.yml`.
