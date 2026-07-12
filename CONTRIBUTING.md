# Contributing to IBEX Harness

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold it.

Thank you for contributing. This repository is a production-grade, security-sensitive monorepo. Please read this guide before opening a pull request.

## PR-only workflow

**Direct pushes to `main` are not allowed** once branch protection is enabled.

1. Create a feature branch from `main`.
2. Make your changes.
3. Open a pull request against `main`.
4. Ensure all required CI checks pass.
5. Merge via GitHub (squash or merge commit per repo settings).

Emergency fixes use a short-lived `hotfix/*` branch and the same PR process—no direct commits to `main`.

## Branch naming

Use the conventions in [web/engineering/DEVELOPMENT_GUIDE.md](web/engineering/DEVELOPMENT_GUIDE.md) §6.1:

- `feature/IBEX-1234-short-description`
- `fix/IBEX-1234-short-description`
- `chore/IBEX-1234-short-description`
- `security/IBEX-1234-short-description`
- `refactor/IBEX-1234-short-description`
- `perf/IBEX-1234-short-description`

One branch should represent one coherent unit of change.

## Commit messages

Use clear, imperative summaries. Preferred format:

```text
type(scope): short description

Optional body with rationale, breaking changes, or ops notes.
```

Examples: `feat(proxy): add request ID middleware`, `docs(adr): add branch protection policy`, `fix(ci): stabilize gitleaks scan`.

Align with [web/engineering/CODING_STANDARDS.md](web/engineering/CODING_STANDARDS.md) where language-specific rules apply.

## Automated PR review (Copilot)

**GitHub Copilot** (`copilot-pull-request-reviewer`) may comment on pull requests. Treat Copilot feedback as **advisory** only:

- Triage each comment: fix, track in an issue, or reply and dismiss with rationale.
- Copilot does **not** satisfy merge requirements and is not a required status check.

Repository hints for Copilot: [.github/instructions/ibex-harness.instructions.md](.github/instructions/ibex-harness.instructions.md).

## Required CI checks

Every PR must pass these **branch protection** status checks (stable gate names; see [ADR-0008](web/content/docs/adr/0008-security-ci-gates.mdx)):

| Check | Purpose |
|-------|---------|
| `ci-gate-repo` | Fast repo checks: layout, shellcheck, markdownlint, compose (when infra changes), go-mod-tidy/license (when Go changes) |
| `ci-gate-go` | Go/proto lint, tests, smokes, coverage, govulncheck (auto-passes when no Go changes) |
| `ci-gate-web` | Web build and static export guards (auto-passes when no web changes) |
| `ci-gate-security` | Trivy, OSV, bandit, hadolint (auto-passes when no Go/web/deps changes) |
| `gitleaks` | Secret scan (always runs) |
| `semantic-pr-title` | Conventional PR title format |

Path-filtered jobs (Go smokes, `web-build`, `trivy`, etc.) may be **skipped** on docs-only or single-area PRs; gate jobs still run and pass. Cross-cutting changes (`.github/workflows/**`, lockfiles) trigger the full matrix.

**Also run on many PRs (not merge-blocking):** `CodeQL`, `semgrep`, `dependency-review` (deps/lockfile PRs), individual job names under gates.

**Not required for merge (informational / supply chain):** `scorecard`, `sbom` (Grype), `label-pr`.

## PR labels (auto-labeler)

On every PR, [`.github/workflows/labeler.yml`](.github/workflows/labeler.yml) applies labels from [`.github/labeler.yml`](.github/labeler.yml):

| Label | When applied |
|-------|----------------|
| `area/go` | `services/**`, `packages/**`, `go.mod`, `go.sum` |
| `area/web` | `web/**` |
| `area/ci` | `.github/**` |
| `area/benchmarks` | `benchmarks/**`, `web/public/benchmarks/**` |
| `area/docs` | `**/*.md`, `**/*.mdx` |
| `area/infra` | `infra/**`, `osv-scanner.toml` |
| `dependencies` | `go.mod`, `go.sum`, `pnpm-lock.yaml` |

Removed paths drop stale labels (`sync-labels: true`). Labels are informational for reviewers and release notes—not merge gates.

## Local validation (before pushing)

From the repository root:

```bash
# Markdown (matches CI markdownlint job)
npx --yes markdownlint-cli2 "**/*.md" "#node_modules"

# Repo layout guard (matches CI repo-guards job)
bash .github/scripts/check-repo-layout.sh

# Secrets (optional; CI always runs gitleaks)
gitleaks detect --source . --config .gitleaks.toml --redact

# Go lint (buf generate first for auth)
cd packages/proto && buf generate && cd ../..
golangci-lint run ./services/auth/... ./services/proxy/...

# IBEX custom Semgrep rules
semgrep --config .semgrep/rules/ --error .

# Dockerfiles (requires Docker)
find . -name 'Dockerfile*' -not -path './.git/*' -exec docker run --rm -i -v "${PWD}:/workdir" -w /workdir hadolint/hadolint:v2.12.0 hadolint -f tty --config .hadolint.yaml {} \;

# Filesystem CVE scan (install trivy CLI)
trivy fs --severity CRITICAL,HIGH --ignore-unfixed .

# Dependency CVE scan (install osv-scanner CLI)
osv-scanner --recursive .

# SBOM + Grype (install syft and grype CLI; CI uploads table/JSON artifacts only—not Code Scanning SARIF)
syft . -o spdx-json > sbom.spdx.json
grype sbom:sbom.spdx.json --fail-on critical

# Validate workflow YAML
python3 -c "import yaml; import pathlib; [yaml.safe_load(p.read_text()) for p in pathlib.Path('.github/workflows').glob('*.yml')]"

# Coverage (requires Postgres for merged profile; matches CI coverage job)
make compose-test-up
POSTGRES_TEST_DSN=postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable make coverage-report
make coverage-gate
```

CI/security config changes: use [prompts/20-security-ci-audit.txt](prompts/20-security-ci-audit.txt).

**CodeQL (one-time, repo admin):** Disable GitHub **Default** CodeQL setup so the advanced [`.github/workflows/codeql.yml`](.github/workflows/codeql.yml) can upload SARIF (Settings → Code security → Code scanning → CodeQL → use Advanced / disable Default).

**Never commit personal access tokens** in chat, issues, or repository secrets; CI uses the built-in `GITHUB_TOKEN` only.

## Pull request template

Use [.github/pull_request_template.md](.github/pull_request_template.md). Include What/Why, How, Testing, Security, and Docs sections per [web/engineering/DEVELOPMENT_GUIDE.md](web/engineering/DEVELOPMENT_GUIDE.md) §7.

## Code ownership

Default reviewer routing is defined in [.github/CODEOWNERS](.github/CODEOWNERS).

## Security

See [.github/SECURITY.md](.github/SECURITY.md) for vulnerability reporting.

## Further reading

- [web/engineering/DEVELOPMENT_GUIDE.md](web/engineering/DEVELOPMENT_GUIDE.md) — branching, PRs, CI expectations
- [web/engineering/CODING_STANDARDS.md](web/engineering/CODING_STANDARDS.md) — style and quality bar
- [docs/adr/ADR-0003-branch-protection-and-merge-policy.md](docs/adr/ADR-0003-branch-protection-and-merge-policy.md) — branch protection policy
- [docs/adr/ADR-0008-security-ci-gates.md](docs/adr/ADR-0008-security-ci-gates.md) — security scanning CI gates
