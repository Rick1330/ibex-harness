---
description: Run CodeScene, SonarQube and Codacy locally against the change set, fix every finding, then run the repo gates. Do not push until green.
---

Run the **local** quality gate before any push. The goal is that the PR never discovers a problem we could have found
here. Do not open or update a PR until this command is green.

## 0. Establish the change set

```bash
git status --short
git diff --stat
git diff --name-only
```

Collect the changed source files. Skip generated output, lockfiles, and vendored assets.

## 1. CodeScene — code health

- `codescene_code_health_review` on the changed files, or `codescene_analyze_change_set` for the whole change.
- `codescene_pre_commit_code_health_safeguard` immediately before committing.
- Fix every regression the review reports. Do not lower a CodeScene threshold to pass.

## 2. SonarQube — bugs, security, code smells

- `sonarqube_analyze_code_snippet` for each changed source file. Pass `filePath` relative to the repository root (the
  workspace is mounted, so do not paste file content) and set `language`.
- Fix BLOCKER and CRITICAL first, then HIGH, then the rest.
- For existing project findings: `sonarqube_search_sonar_issues_in_projects` (project key `Rick1330_ibex-harness`).
- Do not mark an issue false-positive or accepted without a written reason.

## 3. Codacy — patterns, duplication, security

- `codacy_cli_analyze` with `rootPath` set to the repository root; pass `file` for targeted analysis.
  Run `codacy_cli_install` first if the CLI is missing.
- For repository findings: `codacy_list_repository_issues` with `provider: gh`, `organization: Rick1330`,
  `repository: ibex-harness`.
- Security findings: `codacy_search_repository_srm_items`.

## 4. Repository gates

```bash
make check
golangci-lint run ./services/auth/... ./services/proxy/...
go test ./packages/... ./services/auth/... ./services/proxy/...
# coverage when Go or Python changed
make coverage-report && make coverage-gate
# site when site/ changed
bash infra/scripts/agent-docs-check.sh full
# console when services/console changed
pnpm --filter @ibex/console typecheck && pnpm --filter @ibex/console lint && pnpm --filter @ibex/console test
```

## 5. Report

Produce a short table: tool → findings → fixed → remaining. For anything remaining, state why it is not fixable in this
change and what follows it. Never push with an unexplained finding.

Only after every section is green: commit with `-s` (DCO), then push once.
