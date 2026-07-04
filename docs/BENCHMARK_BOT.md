# IBEX Benchmark Bot — specification (follow-up milestone)

This document defines the **external GitHub App** that will publish benchmark data to `ibex-harness` after merge. Implementation lives in a **separate repository** (not in this monorepo).

Related: [ADR-0024](/docs/adr/0024-benchmark-data-publishing-model) (accepted publishing model for `ibex-harness`).

## Goals

- Publish validated `docs/app/public/benchmarks/benchmark-data.json` and `badge.svg` to `main` via **pull request**, never by pushing to contributor PR branches.
- Provide **cryptographically attributable** bot identity (GitHub App), not spoofable git author strings.
- Use **least-privilege** tokens with short lifetimes and documented rotation.

## Non-goals

- Writing benchmark JSON onto feature PR branches (removed from `ibex-harness` workflows).
- Running benchmark collection inside the bot repo (collection stays in `ibex-harness` `Benchmarks` workflow).

## Architecture

```text
ibex-harness                          ibex-benchmark-bot (new repo)
────────────────                      ─────────────────────────────
Benchmarks workflow ──artifact──►     workflow_run / repository_dispatch
  (main / schedule)                         │
                                            ▼
                                      Validate artifact (reuse validate_published_data.py logic)
                                            │
                                            ▼
                                      GitHub App installation token
                                            │
                                            ▼
                                      Branch chore/bench-data-{run_number}
                                      PR: chore(bench): weekly benchmark data update
```

## GitHub App permissions (minimal)

| Permission | Access | Reason |
| --- | --- | --- |
| Contents | Read & write | Create branch, commit JSON + badge on bot branch |
| Pull requests | Read & write | Open/update data PR |
| Actions | Read | Locate successful benchmark workflow run + download artifact |
| Metadata | Read | Required by GitHub Apps |

Do **not** grant administration, workflows write, or org-level scopes beyond the single target repository.

## Token lifecycle

1. Generate a GitHub App in the org/user account; store **App ID** and **private key** in the bot repo secrets (or org secrets scoped to the bot repo only).
2. Install the app on **`Rick1330/ibex-harness`** only (no all-repositories installation).
3. Bot workflow exchanges JWT → **installation access token** (1-hour TTL) per job; never log token values.
4. Document private key rotation: generate new key in App settings, update secret, revoke old key after successful deploy.

## Identity verification

Trust **GitHub API commit metadata**, not git config author strings:

- Commits created via the App show `committer.type == "Bot"` and a fixed login (e.g. `ibex-benchmark-bot[bot]`).
- Harness workflows must not treat arbitrary author emails as proof of automation.
- Future optional hardening: require signed commits from the App or compare `commit.verification.verified`.

## Trigger

Preferred: `workflow_run` in the bot repo watching `Rick1330/ibex-harness` workflow **Benchmarks** on `completed` + `main` + success.

Alternative: `repository_dispatch` from `ibex-harness` `open-benchmark-data-pr` replacement step (narrow event payload: run ID, head SHA, artifact name).

## Publish flow

1. Download `benchmark-data` artifact from the triggering run (Actions API).
2. Run schema validation (port or subprocess `validate_published_data.py` from a pinned harness ref).
3. Create branch `chore/bench-data-{GITHUB_RUN_NUMBER}` from latest `main`.
4. Commit files under `docs/app/public/benchmarks/` with message `chore(bench): weekly benchmark data update`.
5. Open PR with conventional title/body including workflow run link and head SHA.
6. Enable auto-merge only after required harness checks pass (same as human PRs).

## Security requirements

- **No `contents: write` on fork PR workflows** in `ibex-harness`; bot never checks out untrusted PR code with write token.
- Reject artifacts when validation fails; do not commit partial JSON.
- Rate-limit and audit: log run ID, head SHA, PR URL; no secrets or raw tokens in logs.
- Bot repo branch protection: require review for App credential or workflow changes.

## Migration from interim workflow

When the app is live:

1. Remove `open-benchmark-data-pr` from [`.github/workflows/benchmark.yml`](../.github/workflows/benchmark.yml).
2. Add `workflow_run` trigger stub or dispatch call documented here.
3. Verify weekly `main` benchmark run → bot PR → merge updates docs site.

## Implementation checklist (bot repo)

- [ ] Create GitHub App + installation on `ibex-harness`
- [ ] Bot repo with pinned third-party actions (same policy as harness `validate-action-pins.sh`)
- [ ] Workflow: artifact download + validate + create PR via App token
- [ ] Threat model review (fork PRs, token scope, artifact tampering)
- [ ] Runbook: rotation, failure alerts, manual re-publish
- [ ] Remove interim `open-benchmark-data-pr` job from harness

## Open questions for architecture review

1. Single bot repo vs org-level reusable workflow — **recommend separate repo** for credential isolation.
2. Auto-merge bot PRs vs manual maintainer merge — **recommend manual merge** until stable.
3. Whether benchmark JSON on `main` should require CODEOWNERS review — **yes** (already in [`.github/CODEOWNERS`](../.github/CODEOWNERS)).
