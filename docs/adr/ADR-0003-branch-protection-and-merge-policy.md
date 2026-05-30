# ADR-0003: Branch protection and merge policy

- **Status:** Accepted
- **Date:** 2026-05-30
- **Authors:** IBEX Harness team

## Context

Foundation bootstrap ([ADR-0002](ADR-0002-repo-foundation-bootstrap.md)) added CI (repo guards, markdownlint, gitleaks) but `main` remained unprotected. Direct pushes were still possible. GitHub branch protection requires **stable status check context names**; job display names were normalized to `repo-guards`, `markdownlint`, and `gitleaks`.

The repository is maintained solo today but must scale to team review without re-architecting policy.

## Decision

### Stable required status checks

| CI job id | Status check context (branch protection) |
|-----------|---------------------------------------------|
| `repo-guards` | `repo-guards` |
| `markdown` | `markdownlint` |
| `secrets` | `gitleaks` |

### Solo mode (active now)

Apply to branch `main` after the governance PR merges:

| Setting | Value |
|---------|--------|
| Require pull request before merge | Yes |
| Required approving review count | **0** (author cannot self-approve on GitHub) |
| Require CODEOWNERS review | No |
| Required status checks | `repo-guards`, `markdownlint`, `gitleaks` |
| Require branches up to date | Yes (`strict`) |
| Require conversation resolution | Yes |
| Allow force pushes | No |
| Allow branch deletion | No |
| Include administrators | Yes (`enforce_admins: true`) |

**Rationale for zero approvals:** Requiring ≥1 approval blocks a solo maintainer from merging their own PRs. Self-review happens in the PR description and checklist until additional reviewers exist.

**Rationale for `enforce_admins: true`:** Avoids a bypass habit; hotfixes use `hotfix/*` + PR like any other change.

### Team mode (upgrade later)

When multiple reviewers exist:

| Setting | Value |
|---------|--------|
| Required approving review count | 1 (docs/chore) / 2 (features) per [DEVELOPMENT_GUIDE.md](../DEVELOPMENT_GUIDE.md) §7.3 |
| Require CODEOWNERS review | Yes |
| Dismiss stale reviews on push | Yes |
| Required status checks | Unchanged (`repo-guards`, `markdownlint`, `gitleaks`) |
| Other solo settings | Unchanged |

Split approval rules by path or label may require GitHub **rulesets** in a follow-up ADR.

### Governance files

- [.github/CODEOWNERS](../../.github/CODEOWNERS) — default `* @Rick1330`
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — PR workflow and local checks
- [.github/SECURITY.md](../../.github/SECURITY.md) — vulnerability reporting pointer

## Consequences

### Positive

- `main` stays releasable; all changes are traceable via PRs.
- CI check names are stable for branch protection configuration.
- Clear upgrade path to team-scale review.

### Negative

- Solo workflow adds PR overhead vs direct push (intentional).
- Branch protection must be applied on GitHub after merge (not encoded in git).

## Apply branch protection (GitHub)

After merge, register check names on a PR, then apply via Settings → Branches or:

```bash
gh api --method PUT \
  repos/Rick1330/ibex-harness/branches/main/protection \
  -f required_status_checks[strict]=true \
  -f required_status_checks[checks][]=context=repo-guards \
  -f required_status_checks[checks][]=context=markdownlint \
  -f required_status_checks[checks][]=context=gitleaks \
  -F enforce_admins=true \
  -F required_conversation_resolution=true \
  -F allow_force_pushes=false \
  -F allow_deletions=false \
  -f required_pull_request_reviews[dismiss_stale_reviews]=false \
  -f required_pull_request_reviews[require_code_owner_reviews]=false \
  -f required_pull_request_reviews[required_approving_review_count]=0
```

## References

- [CONTRIBUTING.md](../../CONTRIBUTING.md)
- [DEVELOPMENT_GUIDE.md](../DEVELOPMENT_GUIDE.md) §6.3, §7
- [.github/workflows/ci.yml](../../.github/workflows/ci.yml)
