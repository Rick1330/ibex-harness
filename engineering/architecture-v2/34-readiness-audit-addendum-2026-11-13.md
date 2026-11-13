# Readiness audit addendum — 2026-11-13

**Title:** What has closed since the 2026-11-09 audit, what is still open and on what, and which gates are documented as running but do not run in CI.
**Base:** `main` at `708a42d6` (2026-11-13).
**Status:** Addendum to [`27-v1-readiness-audit.md`](27-v1-readiness-audit.md), which is a dated snapshot and is not rewritten. This document changes no status, promotes no ledger row, and closes no gap by itself; no status value or review date in [`00-status-and-evidence.md`](00-status-and-evidence.md) changes. It re-verifies the rows it names against the tree at the base above. Sequencing lives in [`31-v1-release-plan-2026-11-09.md`](31-v1-release-plan-2026-11-09.md); runtime-row evidence lives in [`32-ledger-review-2026-11-09.md`](32-ledger-review-2026-11-09.md); model provenance lives in [`../MODEL_INVENTORY.md`](../MODEL_INVENTORY.md).

Every file:line below was opened at the base commit. Where a claim could not be verified from the tree, the row says so instead of asserting it.

## 1. Rows closed since the audit

Seven rows are addressed here. Five are closed outright; two (P1-04, P1-05) are closed for the supported profile only, and their audit sentence is still true of the reference file it also cites.

**P1-04 / P1-05 — TEI unpinned in any profile.** Audit finding: "TEI has no pinned image or model anywhere" (`27-v1-readiness-audit.md`:95-96).
Closed for `v1-single-node` by `infra/compose/v1-single-node/compose.yml`:358 and :361-362 — the image is digest-pinned (`text-embeddings-inference:cpu-1.9.4@sha256:2538ea1c…`) and the weights carry `--model-id=BAAI/bge-m3` with `--revision=5617a9f61b028005a4858fdac845db406aefb181`.
Residual, stated precisely: the audit's "in any profile" is now false only of the supported profile. `infra/reference/tei-embeddings.compose.yaml`:47 still floats `text-embeddings-inference:cpu-1.6` and :56-58 passes `--model-id` with no `--revision`. That file is marked "REFERENCE ONLY" at :1 and is not started by `make compose-dev-up`. The capability stays provisional because no embedding-quality evidence exists: the ledger's P1-30/P1-31 row is `provisional` (`00-status-and-evidence.md`:26).

**P1-30 — search never filters by `embedding_model`.** Audit finding: "search never filters by `embedding_model`" (`27-v1-readiness-audit.md`:120).
Closed as an optional fence: `services/memory/app/schemas/search.py`:25-27 declares `embedding_model` with `default=None`; `services/memory/app/routers/memory_search_support.py`:181 forwards it into `find_similar`; `services/memory/app/read/repository.py`:194-204 documents and threads it; `services/memory/app/vectorstore/pgvector_store.py`:43-44 applies it in `SEARCH_SQL` (`CAST(:embedding_model AS text) IS NULL OR embedding_model = …`).
Residual: the fence is off by default (``default=None``), and it bounds the vector channel only — the full-text channels are not fenced, which the repository docstring at `repository.py`:204-212 states and `schemas/search.py`:20-22 repeats. No re-embed path exists (see P1-31), so turning the fence on would drop the existing corpus.

**P1-31 — no model provenance inventory.** Audit finding: "No model provenance inventory (model, revision, licence, fallback); extraction defaults are floating aliases" (`27-v1-readiness-audit.md`:121).
Closed as an inventory: `engineering/MODEL_INVENTORY.md` and `infra/model-inventory.v1.json` exist and record model id, dimensions, revision and fallback per deployment profile; the document's own status line is `provisional` (`MODEL_INVENTORY.md`:3).
Residual: `provisional` is the recorded status, not `accepted`; licence and weights-revision fields are incomplete per the ledger row (`00-status-and-evidence.md`:26); and no re-embed task exists — `services/worker/app/task_names.py`:5 lists `ibex.worker.embedding.noop` as the only embedding task, and `re-embed` appears only in comments (`read/repository.py`:204, `vectorstore/pgvector_store.py`:123-124).

**P1-34 — no "data, not instructions" framing on memory-only assemblies.** Audit finding: "The 'data, not instructions' framing is emitted only when a directive exists; memory-only assemblies lack it" (`27-v1-readiness-audit.md`:124).
Closed by `services/context/app/formatter.py`:120-121 — when there is no directive and a memory block exists, `_data_framing_sentence(assembly_nonce)` is appended as the leading section; `formatter.py`:204-206 builds it, and the directive path keeps the same sentence at `:215`. Covered by `services/context/tests/test_formatter.py`:233 and :304.
Residual: context assembly remains `provisional` for reasons unrelated to this row (`00-status-and-evidence.md`:27 — shared caller token, unsigned `PrincipalContext`, no hosted evidence); this row's own finding is closed.

**P1-35 — no injection quarantine.** Audit finding: "No injection-risk classifier or quarantine; instruction-like content is stored active and injected" (`27-v1-readiness-audit.md`:125).
Closed by `services/memory/app/pipeline/stages.py`:86-89 — `InjectionStage` sets `ctx.status = "quarantined"`, records the reason, sets `ctx.stop = True`, and the docstring at :71-73 states the pipeline then takes the quarantine persist path with no embedding, no dedup and no index write. The stage is registered unconditionally in the write pipeline at `services/memory/app/write/factory.py`:71, ahead of the PII stage.
Residual: this is a heuristic classifier over the write path only; the ledger's memory row stays `shipped-local`/`provisional` and nothing here promotes it. No evidence of classifier precision/recall is recorded.

**P1-51 — README evidence wording.** Audit finding: "README says the platform 'attaches evidence to every request'; the finalizer is post-response and the relay is default-off" (`27-v1-readiness-audit.md`:141).
Closed: `README.md`:14-16 now reads "attempts best-effort post-response evidence for governed sessions when the PostgreSQL evidence plane is configured". The words "attaches evidence to every request" no longer occur (`grep -n "attaches evidence" README.md` returns nothing).
Residual: none for this row; the evidence plane's own status is unchanged (`00-status-and-evidence.md`:33).

**What did not change.** No capability status is promoted, and no status value or review date in the ledger moves; the only ledger edit is the pointer paragraph at the top of `00-status-and-evidence.md`. The three claim-bearing sources (`00-status-and-evidence.md`, `site/app/data/ledger.ts`, `site/content/docs/02.architecture/05.status-and-evidence.md`) therefore stay in sync without a content change.

## 2. Rows still open, with the blocker

One line each. Blocker classes: **owner decision**, **credential**, **workflow/branch-protection**, **benchmark stack**, **infrastructure**, **product**.

### Deliverability and operator product

| Row | What is still open (file:line) | Blocker |
|---|---|---|
| P0-04 | No `login`/`logout`/`refresh` page under `services/console/app/pages/`; the e2e suite mints a fixture cookie at `services/console/e2e/live-stack.mjs`:49-53 | product |
| P0-05 | Every Console BFF route is a read: 20 `*.get.ts` and 0 `*.post/put/patch/delete.ts` under `services/console/server/` | product (D-C) |
| W9.1 | Login/refresh/logout pages and httpOnly-cookie BFF routes (`31-v1-release-plan-2026-11-09.md`:166) | product |
| W9.2 | Cookie-capable mutations with CSRF, or a declared read-only 1.0 (`31-v1-release-plan-2026-11-09.md`:167) | owner decision (D-C) |
| W9.3 | No tenant provisioning route: `services/api/app/routers/organizations.py`:30-85 has get/patch/suspend/delete only, no create | product |
| W9.4 | 2 of 10 core surfaces are still `preview` in `services/console/shared/operator/surfaces.ts`:107-108 | product |
| P0-22 | The only recorded start is `IBEX_ENV=staging`, `IBEX_LLM_MODE=mock` (`29-v1-single-node-start-record-2026-11-07.md`:13) | infrastructure |

### Recovery

| Row | What is still open (file:line) | Blocker |
|---|---|---|
| P0-09 | `backup.enabled: true` renders nothing — no template exists for it (`infra/helm/ibex-harness/values.yaml`:69-70; no `backup` template under `templates/`), and `v1-single-node` has no backup service (`grep -c backup infra/compose/v1-single-node/compose.yml` → 0) | infrastructure |
| P0-10 | The committed drill is a `pg_dump` fallback with `rpo_pass: false` (`infra/scripts/platform/evidence/4p5-restore-drill/restore-drill-report.json`:13, :15) | infrastructure |
| P0-11 | Classes are defined, no signed numbers (`15-runtime-operations-and-recovery.md`:11) | owner decision (D-D) |
| W4.1 | No backup service, no WAL archiving, no off-host repository (`31-v1-release-plan-2026-11-09.md`:93) | infrastructure + owner decision (D-D) |
| W4.2 | No archive-lag or backup-freshness alert (`31-v1-release-plan-2026-11-09.md`:94) | infrastructure |
| W4.3 | No measured PITR drill against a signed RTO (`31-v1-release-plan-2026-11-09.md`:95) | infrastructure |
| W4.4 | RPO/RTO table unsigned (`31-v1-release-plan-2026-11-09.md`:96) | owner decision (D-D) |
| W4.5 | `IBEX_CREDENTIALS_MASTER_KEY` has no separate backup or recovery step (`31-v1-release-plan-2026-11-09.md`:97) | infrastructure |
| W4.6 | No `v1-backup` / `v1-restore` Make targets (`grep -n "v1-backup\|v1-restore" Makefile` → no match; the targets present are `v1-secrets`, `v1-up`, `v1-bootstrap-pat`, `v1-down`, `v1-migrate`, `v1-provision`, `v1-logs`, `v1-ps`) | product |

### Contracts

| Row | What is still open (file:line) | Blocker |
|---|---|---|
| P0-12 | `buf-breaking` is advisory: `continue-on-error: true` at `.github/workflows/ci.yml`:323, and absent from `.github/branch-protection-main.json` (required contexts are the `ci-gate-*` set, `gitleaks`, `semantic-pr-title`) | workflow/branch-protection |
| P0-13 | `infra/scripts/api-breaking.sh` exists and passes locally (`31-v1-release-plan-2026-11-09.md`:130) but no workflow runs it: `grep -c api-breaking .github/workflows/ci.yml` → 0 | workflow/branch-protection |
| P0-14 | REST registry is complete and gated; gRPC is service-level only and MCP is out of scope (`31-v1-release-plan-2026-11-09.md`:49; `contracts/rest-route-registry.json`:624) | workflow/branch-protection |
| W5.1 | `buf-breaking` not a required check (`ci.yml`:323) | workflow/branch-protection |
| W5.4 | Deprecation record is empty (`contracts/deprecations.json`: `"entries": []`) and no emitter writes `Deprecation`/`Sunset`/`Link` (`31-v1-release-plan-2026-11-09.md`:132) | product |
| W5.5 | The MCP descriptor check is record-to-surface, not a previous-commit diff, so a schema change carries no deprecation record (`31-v1-release-plan-2026-11-09.md`:133) | product |

### Release integrity

| Row | What is still open (file:line) | Blocker |
|---|---|---|
| P0-15 | `.version-release-manifest.json`:1 is `{".":"0.1.9"}`; the release workflows need `VERSION_RELEASE_TOKEN` (`31-v1-release-plan-2026-11-09.md`:50) | credential |
| W7.1 | Version Release has never run green (`31-v1-release-plan-2026-11-09.md`:154) | credential |
| W7.2 | Tags are lightweight and unsigned, no tag protection (`31-v1-release-plan-2026-11-09.md`:155) | owner decision (D-A) |
| W7.3 | Manifest is neither schema-validated nor signed at upload; no per-image SBOM; no `cosign verify` (`31-v1-release-plan-2026-11-09.md`:156) | product |
| W7.4 | `apt-get upgrade` at build time in memory/embedder (`31-v1-release-plan-2026-11-09.md`:157) | product |
| W7.5 | No `v1-smoke` target or job exists — `v1-smoke` appears only in `31-v1-release-plan-2026-11-09.md`:158 and :200 | workflow/branch-protection |

### Tenancy and security

| Row | What is still open (file:line) | Blocker |
|---|---|---|
| P0-06 | No service DSN has moved to its capability login — every Compose DSN is the owner `POSTGRES_USER` default `ibex` (`infra/compose/v1-single-node/compose.yml`:121, :159, :201, :257, :303; `grep -c ibex_app` → 0), corroborated by `00-status-and-evidence.md`:37 | owner decision (DSN swap) |
| P0-21 | Route-level operator negatives are green; the two-tenant browser journey and a proxy/chat negative are missing (`31-v1-release-plan-2026-11-09.md`:56) | product |
| P1-12 | `BILLING_READ` is defined (`packages/authclient/src/authclient/permissions.py`:20) but unenforced: the read context depends on `require_token` only (`services/api/app/routers/billing.py`:56-62) while the write context requires `RequireOrgSettings` (:65-70) | product |
| P1-13 | `GET …/legal-holds` is authentication-only (`services/api/app/routers/legal_holds.py`:31-38) while the mutation requires `RequireLegalHoldManage` (:41-45) | product |
| P1-14 | `mcp-memory` returns `allowed_hosts=[]` with DNS-rebinding protection on (`services/mcp-memory/app/server.py`:269-271); the localhost allowlist at :261 is test-only | infrastructure |

### Observability and quality evidence

| Row | What is still open (file:line) | Blocker |
|---|---|---|
| P0-19 | Routing exists, delivery does not: the receivers point at the in-network placeholder `http://alert-receiver:8080/alerts/{page,digest}` (`infra/monitoring/alertmanager/alertmanager.yml`:48, :53), and no workflow runs the routing gate (see §3.3) | owner decision + workflow |
| P0-20 | All 28 published HNSW runs are unrecorded — no `provenance` block, so no runner CPU/RAM, commit, gold-set hash or seed (`site/public/benchmarks/hnsw-benchmark-data.json`; `python3 benchmarks/scripts/check_reproducibility.py` → "28 of 28 run(s) are unrecorded") | benchmark stack |
| W10.2 | `graph_mode_distinguished` **is** implemented and gated (`benchmarks/memory/ranking_quality/check_mode_gate.py`:79, :166-172); open is only `full_graph == hybrid_rerank`, which needs a gold-set change and a real run, plus the decision whether a v2 number is published at all (`31-v1-release-plan-2026-11-09.md`:176) | benchmark stack + owner decision |

**P0-20 correction.** The plan's shorthand "no CI invocation of the publisher" (`31-v1-release-plan-2026-11-09.md`:53) did not hold up against the tree: the artifact is collected by `collect-hnsw-benchmarks` (`.github/workflows/memory-benchmark.yml`:95) and overlaid from that run in `.github/workflows/ci.yml`:2197-2237. The verified open part is provenance only — the runs carry no `provenance` block, so they are not reproducible evidence.

## 3. Gates documented as running that do not run in CI

Each of these is described somewhere as a gate. Each passes locally. None runs on a pull request. Fixing any of them changes `.github/workflows/**`, so each needs an owner.

### 3.1 `benchmarks/scripts/check_reproducibility.py`

Documented as the consumer of the provenance contract (`check_reproducibility.py`:1-12: "Offline, fail-closed reproducibility check for the published benchmark artifacts"). It is invoked from exactly one place:

> `reproducibility_check() { … "$python" benchmarks/scripts/check_reproducibility.py }` — `infra/scripts/dev-tool.sh`:387-392

`grep -c check_reproducibility .github/workflows/ci.yml` → **0**; no other workflow references it either. So the published artifacts are checked only when a human runs `./infra/scripts/dev-tool.sh reproducibility_check`.

**Exact fix:** add a `reproducibility` step to `ci.yml` `repo-guards` (it needs no service, no database, and no network beyond the pinned requirements) running `python3 benchmarks/scripts/check_reproducibility.py`, and decide whether the four current warnings become failures. Turning the unrecorded-run warning into an error is a separate decision: today it would fail on all 81 published runs.

### 3.2 `benchmarks/scripts/test_pipeline.py`

Described in the ledger as the benchmark gate's own evidence (`00-status-and-evidence.md`:76 records `python3 benchmarks/scripts/test_pipeline.py` → `Ran 40 tests … OK (skipped=1)`). In CI it runs as the second half of a step that installs nothing:

> `- name: Run benchmark pipeline unit tests` / `run: | … python benchmarks/scripts/test_pipeline.py` — `.github/workflows/ci.yml`:946-950

`jsonschema` is installed in the **next** step: `- name: Install uv` at `:951`, then `uv pip install … -r .github/requirements/jsonschema.txt` at `:956-958`. The module under test skips its schema cases when the import is absent:

> `NEEDS_JSONSCHEMA = unittest.skipUnless(check.jsonschema is not None, "needs jsonschema: …")` — `benchmarks/scripts/test_check_reproducibility.py`:33-35

So the schema assertions in `test_check_reproducibility.py` skip, the step stays green, and the run reports a skip that looks benign.

**Exact fix:** install `jsonschema` (or run the step inside the context venv) **before** the pipeline-tests step, and fail rather than skip when it is missing under CI — e.g. pass an env var that turns the `skipUnless` into an error. Both edits are inside `ci.yml` / the test module.

### 3.3 `infra/scripts/check-alert-routing.py`

Described as a `repo-guards` step. It is one locally:

> `repo-guards) … python3 infra/scripts/check-alert-routing.py; bash infra/scripts/slo-rules-check.sh; reproducibility_check ;;` — `infra/scripts/dev-tool.sh`:435

and it self-tests:

> `check-alert-routing: self-test ok (8 fixtures + path refusal)` — `infra/scripts/check-alert-routing.py`:585

The CI `repo-guards` job (`.github/workflows/ci.yml`:25-140) runs the layout, landing-asset, action-pin, credential, DCO, PR-tracking, Helm-chart and inventory guards, and does **not** run `check-alert-routing.py`; `grep -c alert-routing .github/workflows/ci.yml` → **0**. The only CI-adjacent reference is `make repo-guards`, which no workflow calls.

**Exact fix:** add `python3 infra/scripts/check-alert-routing.py` (and, for the same reason, `bash infra/scripts/slo-rules-check.sh`) to the `repo-guards` job step list. Both are pure-Python/shell checks over committed files.

**Consequence to state plainly:** P0-19's routing half is proven only by a local run. Nothing in CI can regress it, and no alert has reached a human.

## 4. Decisions requested

| ID | Decision | What it unblocks |
|---|---|---|
| D-A | `VERSION_RELEASE_TOKEN` + tag-signing key | W7.1-7.3 and P0-15: a green Version Release run, a release PR, and a signed annotated tag |
| D-C | Console 1.0 is login+mutations, or login + declared read-only | W9.2 and P0-05's acceptance criterion; roughly a week of W9 either way |
| D-D | Off-host backup target (S3/MinIO or external POSIX) and the signed RPO/RTO numbers | W4.1, W4.4, P0-11, and the `rpo_pass=true` half of P0-10 |
| — | Approval to wire §3 into CI (three edits under `.github/workflows/**`) | P0-13/P0-19's routing half, plus the reproducibility and pipeline-test gates above |
| — | P0-06: move each service DSN to its capability login | The per-service DSN swap; RLS is enforced only on paths that already pin, and the Compose profile still connects as the owner |

## 5. Method

- `sed -n '<line>p' <file>` on every citation above, at `708a42d6`; drift found while verifying was corrected, not carried forward (the P0-20 publisher claim in §2).
- `npx --yes markdownlint-cli2 --no-globs engineering/architecture-v2/34-readiness-audit-addendum-2026-11-13.md engineering/architecture-v2/00-status-and-evidence.md` → 0 problems.
- `bash infra/scripts/agent-docs-check.sh fast` → 0.
- `node site/scripts/check-claims.mjs` → pass (this file is outside the scanned roots).
- `python3 benchmarks/scripts/check_reproducibility.py` → exit 0, 4 warnings, 81 unrecorded runs.
- Not verified: no hosted origin, cluster, PITR run, or p99 measurement was available to this addendum; rows that need one are recorded with their blocker, not scored.
