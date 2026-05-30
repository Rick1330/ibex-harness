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

## Required CI checks

Every PR must pass these status checks (stable names for branch protection):

| Check | Purpose |
|-------|---------|
| `repo-guards` | Layout, no `.env`, no conflict markers, no large files |
| `markdownlint` | Structural markdown lint |
| `gitleaks` | Secret scan |

## Local validation (before pushing)

From the repository root:

```bash
# Markdown (matches CI markdownlint job)
npx --yes markdownlint-cli2 "**/*.md" "#node_modules"

# Repo layout guard (matches CI repo-guards job)
bash .github/scripts/check-repo-layout.sh

# Secrets (optional; CI always runs gitleaks)
gitleaks detect --source . --config .gitleaks.toml --redact
```

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
