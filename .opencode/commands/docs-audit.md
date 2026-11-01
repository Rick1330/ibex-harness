---
description: Repo-wide documentation audit — lint every Markdown file, check the status ledger, and report what is stale.
---

Run a whole-repository documentation sweep. This is the periodic "keep-up" pass, not the pre-push check.

```bash
bash infra/scripts/agent-docs-check.sh repo
```

That lints **every** Markdown file in the repository (not just changed ones) and runs the status-ledger claim check.

Then review and fix:

1. **Lint failures** — fix the Markdown. Do not add files to the ignore list to silence a real problem.
2. **Broken relative links** in `engineering/` and root docs — update the target or the link.
3. **Stale status claims** — confirm `engineering/architecture-v2/00-status-and-evidence.md`,
   `site/app/data/ledger.ts`, and `site/content/docs/02.architecture/05.status-and-evidence.md` still agree, and that
   `verifiedDate` is not expired.
4. **Orphaned docs** — a page that no index links to, or a doc describing behaviour that no longer exists.
5. **Missing docs** — a new flag, env var, endpoint, or service with no documentation.

For content updates, use the `doc-updater` subagent and run `/docs-sync` afterwards. Report what you changed and what
still needs a human decision.
