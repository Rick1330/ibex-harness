# Contributing to IBEX Harness

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

Use the conventions in [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md) §6.1:

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

Align with [docs/CODING_STANDARDS.md](docs/CODING_STANDARDS.md) where language-specific rules apply.

## Automated PR review (Copilot)

**GitHub Copilot** (`copilot-pull-request-reviewer`) may comment on pull requests. Treat Copilot feedback as **advisory** only:

- Triage each comment: fix, track in an issue, or reply and dismiss with rationale.
- Copilot does **not** satisfy merge requirements and is not a required status check.

Repository hints for Copilot: [.github/instructions/ibex-harness.instructions.md](.github/instructions/ibex-harness.instructions.md).

## Required CI checks

Every PR must pass these status checks (stable names for branch protection; see [ADR-0008](docs/adr/ADR-0008-security-ci-gates.md)):

| Check | Purpose |
|-------|---------|
| `repo-guards` | Layout, no `.env`, no conflict markers, no large files |
| `markdownlint` | Structural markdown lint |
| `gitleaks` | Secret scan |
| `CodeQL` | Dataflow SAST (Go, Python, JS/TS) |
| `semgrep` | Community SAST + `.semgrep/rules/` IBEX invariants |
| `trivy` | Filesystem CVE scan (CRITICAL/HIGH, unfixed ignored) |
| `osv-scan` | Lockfile CVE scan (OSV database) |
| `golangci-lint` | Go lint (auth + proxy) |
| `bandit` | Python security lint (skips until `services/memory` exists) |
| `hadolint` | Dockerfile best practices |

Not required for merge (informational / supply chain): `scorecard`, `sbom` (Grype), `buf-lint`, `go-services`, smoke tests.

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

# SBOM + Grype (install syft and grype CLI)
syft . -o spdx-json > sbom.spdx.json
grype sbom:sbom.spdx.json --fail-on critical

# Validate workflow YAML
python3 -c "import yaml; import pathlib; [yaml.safe_load(p.read_text()) for p in pathlib.Path('.github/workflows').glob('*.yml')]"
```

CI/security config changes: use [prompts/20-security-ci-audit.txt](prompts/20-security-ci-audit.txt).

**CodeQL (one-time, repo admin):** Disable GitHub **Default** CodeQL setup so the advanced [`.github/workflows/codeql.yml`](.github/workflows/codeql.yml) can upload SARIF (Settings → Code security → Code scanning → CodeQL → use Advanced / disable Default).

**Never commit personal access tokens** in chat, issues, or repository secrets; CI uses the built-in `GITHUB_TOKEN` only.

## Pull request template

Use [.github/pull_request_template.md](.github/pull_request_template.md). Include What/Why, How, Testing, Security, and Docs sections per [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md) §7.

## Code ownership

Default reviewer routing is defined in [.github/CODEOWNERS](.github/CODEOWNERS).

## Security

See [.github/SECURITY.md](.github/SECURITY.md) for vulnerability reporting.

## Further reading

- [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md) — branching, PRs, CI expectations
- [docs/CODING_STANDARDS.md](docs/CODING_STANDARDS.md) — style and quality bar
- [docs/adr/ADR-0003-branch-protection-and-merge-policy.md](docs/adr/ADR-0003-branch-protection-and-merge-policy.md) — branch protection policy
- [docs/adr/ADR-0008-security-ci-gates.md](docs/adr/ADR-0008-security-ci-gates.md) — security scanning CI gates
