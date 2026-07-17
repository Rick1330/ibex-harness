# Contributing to IBEX Harness

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold it.

Thank you for contributing. This repository is a production-grade, security-sensitive monorepo. Please read this guide before opening a pull request.

## PR-only workflow

**Direct pushes to `main` are not allowed** once branch protection is enabled.

1. **Open a tracker issue** using a repo template ([feature request](.github/ISSUE_TEMPLATE/feature_request.md) or [bug report](.github/ISSUE_TEMPLATE/bug_report.md)). Fill every section.
2. Create a feature branch from `main`.
3. Make your changes.
4. Open a pull request against `main` using [.github/pull_request_template.md](.github/pull_request_template.md).
5. In the PR body, include a close keyword: `Closes #123` (or `Fixes` / `Resolves`). Merging the PR **closes the issue**.
6. In the issue body or a comment, reference the PR: `Implementation PR: #456` so the link is bidirectional.
7. Ensure all required CI checks pass.
8. Merge via GitHub (squash or merge commit per repo settings).

CI enforces this contract in `repo-guards` ([`.github/scripts/check-pr-tracking.sh`](.github/scripts/check-pr-tracking.sh)). Dependabot and GitHub Actions automation PRs are exempt.

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

## Developer Certificate of Origin (DCO)

Every commit must include a **Signed-off-by** line asserting you have the right to contribute under the project license ([MIT](LICENSE)). This satisfies [Developer Certificate of Origin](https://developercertificate.org/) requirements (OpenSSF OSPS-LE-01.01).

Add to each commit message:

```text
Signed-off-by: Your Name <your.email@example.com>
```

Use the same name and email as your Git author. For squash merges, ensure the final commit includes `Signed-off-by` (GitHub preserves it from the PR branch when present on commits).

CI enforces sign-off on pull requests via the `repo-guards` job ([`.github/scripts/check-dco-signoff.sh`](.github/scripts/check-dco-signoff.sh)). Automation commits from `github-actions[bot]` and `dependabot[bot]` are exempt.

## Reporting defects

Use the public issue tracker for non-security bugs:

1. Open [New issue → Bug report](https://github.com/Rick1330/ibex-harness/issues/new?template=bug_report.md).
2. Include reproduction steps, expected vs actual behavior, and environment (OS, Go/Node versions, compose stack).
3. Redact tokens, passwords, and org identifiers from logs and screenshots.

See also [.github/SUPPORT.md](.github/SUPPORT.md). **Do not** use public issues for security vulnerabilities — follow [.github/SECURITY.md](.github/SECURITY.md).

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

Label colors and descriptions are defined in [`.github/labels.json`](.github/labels.json). Sync to GitHub with:

```bash
bash .github/scripts/sync-github-labels.sh
```

## Local validation (before pushing)

From the repository root:

```bash
# Markdown (matches CI markdownlint job; config is .markdownlint-cli2.jsonc)
npx --yes markdownlint-cli2

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

# Phase 1.5 public site smoke (production default; override with IBEX_SITE_URL)
make verify-phase15
# IBEX_SITE_URL=http://localhost:3000 make verify-phase15   # local static export preview
make coverage-gate
```

CI/security config changes: use [prompts/20-security-ci-audit.txt](prompts/20-security-ci-audit.txt).

## Good first issues

Want a small first contribution? Look for issues labeled [**good first issue**](https://github.com/Rick1330/ibex-harness/labels/good%20first%20issue) or [**help wanted**](https://github.com/Rick1330/ibex-harness/labels/help%20wanted).

Typical starter work: docs typos, markdown/examples, small test additions, CONTRIBUTING clarifications. Follow the PR-only workflow and DCO sign-off above.

## Testing policy

IBEX Harness requires automated tests for behavior changes. This satisfies our [OpenSSF Best Practices](web/engineering/OPENSSF_BEST_PRACTICES.md) enrollment and is enforced in review.

**Policy:** When you add or materially change production behavior (handlers, stores, auth, proxy routing, security boundaries), add or extend tests in the same PR. Prefer the test pyramid in [web/engineering/TESTING_STRATEGY.md](web/engineering/TESTING_STRATEGY.md): unit tests for logic, integration tests for DB/Redis contracts, E2E only for user journeys.

**Bugfixes:** At least half of production bugfix PRs must include a regression test ([TESTING_STRATEGY.md §11.1](web/engineering/TESTING_STRATEGY.md#111-regression-tests-on-bugfixes)).

**How to run tests locally:**

```bash
# Go unit tests (core packages — same scope as CI unit coverage)
go test ./packages/... ./services/auth/... ./services/proxy/...

# Integration tests (Postgres required; includes infra/migrations when tagged)
make compose-test-up
go test -tags=integration ./packages/... ./services/auth/... ./services/proxy/... ./infra/migrations/postgres/...

# Coverage gate (matches CI)
POSTGRES_TEST_DSN=postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable make coverage-report
```

CI runs tests on every PR via [`.github/workflows/ci.yml`](.github/workflows/ci.yml) (`ci-gate-go` always runs; `go-race` and `go-fuzz` run when the workflow detects Go changes via `run_go`). The PR template **Testing** section must list what you ran.

## Linting and static analysis

We treat compiler and linter warnings as defects. Merge-blocking and advisory tools:

| Tool | Scope | CI |
| --- | --- | --- |
| `golangci-lint` | Go services and packages | `ci-gate-go` |
| `buf lint` | Protobuf | `ci-gate-go` |
| Semgrep (`.semgrep/rules/`) | Custom security rules | `ci-gate-security` / PR |
| CodeQL | Go, Python, JavaScript | [`codeql.yml`](.github/workflows/codeql.yml) |
| `ruff` / `bandit` | Python (when present) | `ci-gate-security` |
| ESLint / TypeScript | Dashboard and web | `ci-gate-web` |
| `markdownlint-cli2` | Handwritten `*.md` / `*.mdc` (see exclusions below) | `ci-gate-repo` |
| `govulncheck`, Trivy, OSV | Dependencies | `ci-gate-go` / `ci-gate-security` |

**Policy:** New code must not introduce linter errors. Fix warnings or document false positives in code; do not disable rules without an ADR or security review.

### Generated markdown exclusions

Machine-generated markdown is excluded from `markdownlint-cli2` via [`.markdownlint-cli2.jsonc`](.markdownlint-cli2.jsonc) `ignores` — not by hand-editing each release or bot PR. Today that includes root `CHANGELOG.md` (version release pipeline). Handwritten docs must still pass lint locally and in CI.

Dynamic analysis: Go race detector (`go test -race`) and fuzz smoke (`FuzzParseChatCompletionRequest`) run in CI when `run_go` is true. See [ADR-0008](web/content/docs/adr/0008-security-ci-gates.mdx).

**CodeQL (one-time, repo admin):** Disable GitHub **Default** CodeQL setup so the advanced [`.github/workflows/codeql.yml`](.github/workflows/codeql.yml) can upload SARIF (Settings → Code security → Code scanning → CodeQL → use Advanced / disable Default).

**Never commit personal access tokens** in chat, issues, or repository secrets; CI uses the built-in `GITHUB_TOKEN` only.

## Pull request template

Use [.github/pull_request_template.md](.github/pull_request_template.md). Include **Tracking issue** (`Closes #N`), What/Why, How, Testing, Security, and Docs sections per [web/engineering/DEVELOPMENT_GUIDE.md](web/engineering/DEVELOPMENT_GUIDE.md) §7. The linked issue must reference the PR (`Implementation PR: #…`) so CI can verify bidirectional tracking.

## Code ownership

Default reviewer routing is defined in [.github/CODEOWNERS](.github/CODEOWNERS).

## Security

See [.github/SECURITY.md](.github/SECURITY.md) for vulnerability reporting.

## Further reading

- [web/engineering/GOVERNANCE.md](web/engineering/GOVERNANCE.md) — maintainers, roles, access review
- [web/engineering/DEVELOPMENT_GUIDE.md](web/engineering/DEVELOPMENT_GUIDE.md) — branching, PRs, CI expectations
- [web/engineering/CODING_STANDARDS.md](web/engineering/CODING_STANDARDS.md) — style and quality bar
- [docs/adr/ADR-0003-branch-protection-and-merge-policy.md](docs/adr/ADR-0003-branch-protection-and-merge-policy.md) — branch protection policy
- [docs/adr/ADR-0008-security-ci-gates.md](docs/adr/ADR-0008-security-ci-gates.md) — security scanning CI gates
