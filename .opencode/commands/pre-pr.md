---
description: Full pre-PR gate — quality scanners, security, docs, DCO, and PR body — run before the first push.
---

Run this before pushing a branch for the first time. The goal: the PR opens green, not as a discovery tool.

## 1. Branch and DCO

```bash
git branch --show-current          # must not be main
git log --format='%h %s' origin/main..HEAD
```

Every commit must carry `Signed-off-by`. Fix before pushing:

```bash
git rebase --signoff origin/main   # all commits
git commit --amend -s --no-edit    # only the last commit
```

## 2. Quality scanners

```text
/review-on
/quality-gate
/review-off
```

Fix every finding. Do not push with an unexplained one.

## 3. Security

```text
/security-gate
```

Required when the change touches code, dependencies, auth, configuration, or infrastructure.

## 4. Docs

```bash
bash infra/scripts/agent-docs-check.sh fast
```

Run `full` when `site/` changed, and `/docs-audit` when you edited several documents.

## 5. PR body

Draft it from `.github/pull_request_template.md`:

- **What and Why**, **Tracking issue** (`Closes #N`), **How**
- **Testing**: the exact commands you ran and their result
- **Performance**, **Security**, **Migrations / Ops**, **Docs**
- Definition of Done checklist

Confirm the issue links back (`Implementation PR: #M`).

## 6. Push

Only when all of the above is green:

```bash
git push -u origin HEAD
```

Then let every CI job finish before touching the branch again.
