---
description: Update documentation and the status ledger after a change, then verify the site end to end.
---

Synchronise documentation with the current change set, then prove the site still works.

## 1. Establish what changed

```bash
git status --short
git diff --stat
```

Identify whether the change altered: behaviour, a public contract, a CLI flag, an environment variable, a schema or
migration, a status/evidence claim, or the service inventory.

## 2. Update the sources of truth

- Behaviour or contract change → update the matching page under `site/content/docs/` and any affected
  `engineering/` document.
- Capability or status change → update **all three**, in one change:
  `engineering/architecture-v2/00-status-and-evidence.md`, `site/app/data/ledger.ts`, and
  `site/content/docs/02.architecture/05.status-and-evidence.md`.
- New service or top-level directory → update `services/README.md` / `packages/README.md` and justify it per
  `engineering/FILE_STRUCTURE.md`.
- Release or version change → follow `engineering/RELEASING.md`.

Use the `doc-updater` subagent for large doc sweeps. Do not invent APIs, env vars, or tables that are not in the code.

## 3. Verify

```bash
bash infra/scripts/agent-docs-check.sh full
```

That runs markdownlint on changed files, then the site typecheck, lint, build, and claims/links/redirects checks.
Fix every failure. Do not weaken a check to pass.

## 4. Report

State which documents changed, which claims moved, the exact commands run, and anything you could not verify.
