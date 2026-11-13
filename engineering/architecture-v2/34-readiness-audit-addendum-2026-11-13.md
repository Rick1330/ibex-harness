# Readiness audit addendum — 2026-11-13

**Title:** What has closed since the 2026-11-09 audit, what is still open and on what, and which gates are documented as running but do not run in CI.
**Base:** `main` at `708a42d6` (2026-11-13).
**Status:** Addendum to [`27-v1-readiness-audit.md`](27-v1-readiness-audit.md), which is a dated snapshot and is not rewritten. This document changes no status, promotes no ledger row, and closes no gap by itself; no status value or review date in [`00-status-and-evidence.md`](00-status-and-evidence.md) changes. It re-verifies the rows it names against the tree at the base above. Sequencing lives in [`31-v1-release-plan-2026-11-09.md`](31-v1-release-plan-2026-11-09.md); runtime-row evidence lives in [`32-ledger-review-2026-11-09.md`](32-ledger-review-2026-11-09.md); model provenance lives in [`../MODEL_INVENTORY.md`](../MODEL_INVENTORY.md).

Every file:line below was opened at the base commit. Where a claim could not be verified from the tree, the row says so instead of asserting it.

## 1. Rows closed since the audit

Eight rows are addressed here. Three are closed outright (P1-34, P1-35, P1-51). Five are partial (P1-04, P1-05, P1-27, P1-30, P1-31): each closes part of its audit sentence, and each residual below carries the blocker class from §2.

**P1-04 — the dependency matrix still disagrees across artifacts.** Audit finding at `27-v1-readiness-audit.md`:95 — pgvector mutable in dev/site but pinned in the bundle/CI, Redis and ClickHouse differing across Helm and the sandbox, TEI unpinned.
Closed part: TEI is pinned for `v1-single-node` — `infra/compose/v1-single-node/compose.yml`:358 and :361-362 digest-pin `text-embeddings-inference:cpu-1.9.4@sha256:2538ea1c…` and pass `--model-id=BAAI/bge-m3` with `--revision=5617a9f61b028005a4858fdac845db406aefb181`.
Residual (blocker: infrastructure):
- pgvector is still a mutable `:pg16` tag in `infra/compose/dev/docker-compose.yml`:3 and `site/content/docs/12.deployment/01.docker-compose.md`:48, against the 0.8.6 digest in `infra/compose/bundles/memory-context.yml`:9 and `.github/workflows/ci.yml`:449.
- pgvector disagrees in the chart as well: `infra/helm/ibex-harness/values.yaml`:15 pins `pgvector/pgvector@sha256:ccc6e83d…` with a zero-run tail, and the file's own comment at :16 says to override it with real digests before a drill. It is neither the mutable dev tag nor the bundle digest.
- Redis disagrees: `redis/redis-stack:7.4.0-v1` in `infra/compose/dev/docker-compose.yml`:21 (dev/test), `redis:7.4.2` under a sentinel digest in `infra/helm/ibex-harness/values.yaml`:17.
- Redis is also mutable inside CI: `.github/workflows/ci.yml`:1157 (`embedder-test`), :1975 (`verify-phase25`), and :2548 (`embedder-coverage`) run `image: redis:7`, an unpinned tag with no digest, while the same file pins `redis:7.4.2@sha256:fbdbaea4…` for its other services (`:846`, `:1196`).
- ClickHouse carries a sentinel Helm digest at `infra/helm/ibex-harness/values.yaml`:18 under the excluded Kubernetes profile.
- The reference TEI file still floats: `infra/reference/tei-embeddings.compose.yaml`:47 is `text-embeddings-inference:cpu-1.6` and :56-58 passes `--model-id` with no `--revision`. It is marked "REFERENCE ONLY" at :1 and is not started by `make compose-dev-up`.

**P1-05 — embeddings are not shippable for a semantic claim.** Audit finding at `27-v1-readiness-audit.md`:96. The TEI pin above closes its last sentence; the rest stands.
Residual (blocker: benchmark stack):
- The dev bundle still forces stub geometry: `infra/compose/bundles/memory-context.yml`:70-71 sets `IBEX_EMBEDDING_PROFILE=cpu` with `IBEX_EMBEDDING_DIM=1024`, so the stub writes schema-valid `vector(1024)` of arbitrary geometry — writes succeed and search returns something.
- No embedding-quality evidence exists, so the capability stays `provisional` (`00-status-and-evidence.md`:28: "Not a re-embed path and not a semantic-quality claim").

**P1-27 — `full_graph == hybrid_rerank`, and the mode distinction was ungated.** Audit finding at `27-v1-readiness-audit.md`:117 (`graph_mode_distinguished:false` "is reported but not gated").
Closed part: the gate exists. `benchmarks/memory/ranking_quality/check_mode_gate.py`:243-273 (`declaration_failures`) fails a run that contradicts the baseline's declaration in either direction, and `_declaration` at :159-175 refuses a baseline that omits it; covered by `test_check_mode_gate.py`:146-164 (missing declaration) and :343-379 (contradiction both ways). `.github/workflows/memory-benchmark.yml`:454-465 runs the driver, then the gate.
Residual (blocker: benchmark stack): the corpus-geometry equality itself — `baseline-modes.json`:27-28 records `full_graph == hybrid_rerank` — needs a gold-set change and a real run. See the W10.2 row in §2 and `31-v1-release-plan-2026-11-09.md`:176.

**P1-30 — search never filters by `embedding_model`; embedding models are version-less IDs.** Audit finding at `27-v1-readiness-audit.md`:120.
Closed part: the fence. `services/memory/app/schemas/search.py`:25-27 declares `embedding_model` with `default=None`; `services/memory/app/routers/memory_search_support.py`:181 forwards it into `find_similar`; `services/memory/app/read/repository.py`:194-204 documents and threads it; `services/memory/app/vectorstore/pgvector_store.py`:43-44 applies it in `SEARCH_SQL` (`CAST(:embedding_model AS text) IS NULL OR embedding_model = …`).
Residual (blockers: product, infrastructure):
- **product** — the fence is off by default (``default=None``) and bounds the vector channel only; the full-text channels are not fenced (`repository.py`:206-211; `schemas/search.py`:20-21). Turning it on would drop the existing corpus, because no re-embed path exists (see P1-31).
- **infrastructure** — version-less provenance is not fixed on the serving side: the memory write path records `id@revision` (`MODEL_INVENTORY.md`:48-49), but the embedder records no revision of what it actually served — its TEI request carries only `inputs`, and the served model is whatever the server was started with (`MODEL_INVENTORY.md`:66; `services/embedder/app/tei/client.py`:170-175).

**P1-31 — no model provenance inventory; extraction defaults are floating aliases.** Audit finding at `27-v1-readiness-audit.md`:121.
Closed part: the inventory exists. `engineering/MODEL_INVENTORY.md` and `infra/model-inventory.v1.json` record model id, dimensions, revision and fallback per deployment profile; the document's own status line is `provisional` (`MODEL_INVENTORY.md`:3).
Residual (blocker: owner decision):
- `provisional` is the recorded status, not `accepted`; licence and weights-revision fields are incomplete (`00-status-and-evidence.md`:28), and licence for fifteen of fifteen rows needs an owner (`MODEL_INVENTORY.md`:86-94).
- Extraction defaults are still floating aliases: `services/worker/app/config.py`:181-214 defaults `gpt-4o-mini` and `Qwen2.5-14B-Instruct` on alias-accepting fields, and `MODEL_INVENTORY.md`:39-40 records both as "Floating alias"/"Floating label". The inventory records that they float; it does not pin them.
- No re-embed task exists — `services/worker/app/task_names.py`:5 lists `ibex.worker.embedding.noop` as the only embedding task, and `re-embed` appears only in comments (`read/repository.py`:204, `vectorstore/pgvector_store.py`:123-124).

**P1-34 — no "data, not instructions" framing on memory-only assemblies.** Audit finding: "The 'data, not instructions' framing is emitted only when a directive exists; memory-only assemblies lack it" (`27-v1-readiness-audit.md`:124).
Closed by `services/context/app/formatter.py`:120-121 — when there is no directive and a memory block exists, `_data_framing_sentence(assembly_nonce)` is appended as the leading section; `formatter.py`:204-206 builds it, and the directive path keeps the same sentence at `:215`. Covered by `services/context/tests/test_formatter.py`:233 and :304.
Residual: context assembly remains `provisional` for reasons unrelated to this row (`00-status-and-evidence.md`:29 — shared caller token, unsigned `PrincipalContext`, no hosted evidence); this row's own finding is closed.

**P1-35 — no injection quarantine.** Audit finding: "No injection-risk classifier or quarantine; instruction-like content is stored active and injected" (`27-v1-readiness-audit.md`:125).
Closed by `services/memory/app/pipeline/stages.py`:86-89 — `InjectionStage` sets `ctx.status = "quarantined"`, records the reason, sets `ctx.stop = True`, and the docstring at :71-73 states the pipeline then takes the quarantine persist path with no embedding, no dedup and no index write. The stage is registered unconditionally in the write pipeline at `services/memory/app/write/factory.py`:71, ahead of the PII stage.
Residual: this is a heuristic classifier over the write path only; the ledger's memory row stays `shipped-local`/`provisional` and nothing here promotes it. No evidence of classifier precision/recall is recorded.

**P1-51 — README evidence wording.** Audit finding: "README says the platform 'attaches evidence to every request'; the finalizer is post-response and the relay is default-off" (`27-v1-readiness-audit.md`:141).
Closed: `README.md`:14-16 now reads "attempts best-effort post-response evidence for governed sessions when the PostgreSQL evidence plane is configured". The words "attaches evidence to every request" no longer occur (`grep -n "attaches evidence" README.md` returns nothing).
Residual: none for this row; the evidence plane's own status is unchanged (`00-status-and-evidence.md`:35).

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
| P0-20 | Two artifacts. (a) All 28 published HNSW runs are unrecorded — no `provenance` block, so no runner CPU/RAM, commit, gold-set hash or seed (`site/public/benchmarks/hnsw-benchmark-data.json`; `python3 benchmarks/scripts/check_reproducibility.py` → "28 of 28 run(s) are unrecorded"). (b) The ranking baseline records a run URL but no commit `sha`, `gold_set_hash` or `seed` (`benchmarks/memory/ranking_quality/baseline-modes.json` has none of the three), and `check_mode_gate.py`:185-195 compares gold-set and reranker *labels* (`artifact.gold_set != baseline.gold_set`), not corpus hashes — so HNSW provenance alone does not satisfy the row | benchmark stack (values) + product (a producer and a checker are code work) |
| W10.2 | `graph_mode_distinguished` **is** implemented and gated (`benchmarks/memory/ranking_quality/check_mode_gate.py`:79, :166-172); open is only `full_graph == hybrid_rerank`, which needs a gold-set change and a real run, plus the decision whether a v2 number is published at all (`31-v1-release-plan-2026-11-09.md`:176) | benchmark stack + owner decision |

**P0-20 correction.** The plan's shorthand "no CI invocation of the publisher" (`31-v1-release-plan-2026-11-09.md`:53) did not hold up against the tree: the artifact is collected by `collect-hnsw-benchmarks` (`.github/workflows/memory-benchmark.yml`:95) and overlaid from that run in `.github/workflows/ci.yml`:2197-2237. The verified open part is provenance only — the runs carry no `provenance` block, so they are not reproducible evidence. The gap has a second artifact: `baseline-modes.json` carries no `sha`, `gold_set_hash` or `seed`, and the gate matches labels, so recording HNSW provenance would still leave the ranking baseline unreproducible.

## 3. Gates documented as running that do not run in CI

Each of these is described somewhere as a gate, and each passes locally. This section records where each stood at the audit base: two did not run on a pull request at all, and one ran with its schema assertions skipped. All three are wired in the tree now; §3.1–§3.3 state the fix and the current call site.

### 3.1 `benchmarks/scripts/check_reproducibility.py`

Documented as the consumer of the provenance contract (`check_reproducibility.py`:1-12: "Offline, fail-closed reproducibility check for the published benchmark artifacts"). It is invoked from exactly one place:

> `reproducibility_check() { … "$python" benchmarks/scripts/check_reproducibility.py }` — `infra/scripts/dev-tool.sh`:387-392

`grep -c check_reproducibility .github/workflows/ci.yml` → **0** at the audit base; no other workflow referenced it either. So the published artifacts were checked only when a human ran `./infra/scripts/dev-tool.sh reproducibility_check`. **Wired now:** `.github/workflows/ci.yml`:135-144 installs the validator and runs the checker in the `repo-guards` job (`:25-185`), which feeds `ci-gate-repo` (`:3221`, evaluated at `:3245`).

**The fix that landed:** in the same job that runs it, `jsonschema` is installed from `.github/requirements/jsonschema.txt` with `--require-hashes` **before** invoking `python3 benchmarks/scripts/check_reproducibility.py`. The checker is fail-closed without the import — it reports "jsonschema is not installed" and exits 1 (`check_reproducibility.py`:46-50, :216-217) — and the only other install of that file is in `benchmark-gate` (`.github/workflows/ci.yml`:1161-1166) and into a different interpreter (`services/context/.venv/bin/python`, `:1179-1181`), neither of which the `repo-guards` step can rely on. Then decide whether the four current warnings become failures; turning the unrecorded-run warning into an error today would fail on all 81 published runs.

### 3.2 `benchmarks/scripts/test_pipeline.py` — the schema assertions used to skip

The test file is not missing from CI: `test_pipeline.py` loads `test_check_reproducibility` (`test_pipeline.py`:12-19) and runs on qualifying pull requests in **both** workflows — `benchmark-gate` at `.github/workflows/ci.yml`:1167-1173 and `verify-benchmark-pipeline` at `.github/workflows/benchmark.yml`:106. The ledger records it as the benchmark gate's own evidence (`00-status-and-evidence.md`:78: `Ran 40 tests … OK (skipped=1)`).

What failed is narrower. `test_check_reproducibility.py` used to skip its schema cases when the import was absent. That skip is gone: the module now decides at test time through the `IBEX_REQUIRE_JSONSCHEMA` switch (`benchmarks/scripts/test_check_reproducibility.py`:38, `:45-50`), so a missing validator fails the run with the install command instead of deleting the schema coverage. Both workflows set it and install `jsonschema` first — `benchmark-gate` at `.github/workflows/ci.yml`:1157-1173 and `verify-benchmark-pipeline` at `.github/workflows/benchmark.yml`:105-117 — so the schema assertions run in CI rather than skipping green. The original install was in a step **after** the one that ran the tests; that ordering is reversed.

### 3.3 `infra/scripts/check-alert-routing.py`

Described as a `repo-guards` step. It is one locally:

> `repo-guards) … python3 infra/scripts/check-alert-routing.py; bash infra/scripts/slo-rules-check.sh; reproducibility_check ;;` — `infra/scripts/dev-tool.sh`:435

and it self-tests:

> `check-alert-routing: self-test ok (8 fixtures + path refusal)` — `infra/scripts/check-alert-routing.py`:585

The CI `repo-guards` job (`.github/workflows/ci.yml`:25-185) runs the layout, landing-asset, action-pin, credential, DCO, PR-tracking, Helm-chart and inventory guards, and at the audit base did **not** run `check-alert-routing.py`; `grep -c alert-routing .github/workflows/ci.yml` → **0** then. **Wired now:** `check-alert-routing.py` runs in the `repo-guards` job (`.github/workflows/ci.yml`:101-103), which feeds `ci-gate-repo`; `slo-rules-check` is its own always-run job (`:351-369`), and `ci-gate-repo` both needs it (`:3230`) and evaluates its result (`:3253`).

**The fix that landed:** `python3 infra/scripts/check-alert-routing.py` and `bash infra/scripts/slo-rules-check.sh` are CI steps. Both are pure-Python/shell checks over committed files.

**Consequence to state plainly:** P0-19's routing half is now gated, but no alert has reached a human: the receivers still point at the in-network placeholder (`infra/monitoring/alertmanager/alertmanager.yml`:48, :53), which is P0-19's remaining part.

## 4. Decisions requested

| ID | Decision | What it unblocks |
|---|---|---|
| D-A | `VERSION_RELEASE_TOKEN` + tag-signing key | W7.1-7.3 and P0-15: a green Version Release run, a release PR, and a signed annotated tag |
| D-C | Console 1.0 is login+mutations, or login + declared read-only | W9.2 and P0-05's acceptance criterion; roughly a week of W9 either way |
| D-D | Off-host backup target (S3/MinIO or external POSIX) and the signed RPO/RTO numbers | W4.1, W4.4, P0-11, and the `rpo_pass=true` half of P0-10 |
| — | P0-06: move each service DSN to its capability login | The per-service DSN swap; RLS is enforced only on paths that already pin, and the Compose profile still connects as the owner |

## 5. Method

- `sed -n '<line>p' <file>` on every citation above, at `708a42d6`; drift found while verifying was corrected, not carried forward (the P0-20 publisher claim in §2; ledger line numbers, which the pointer paragraph shifted by two).
- The **§3.1–§3.3 "Wired now" citations were re-verified on the stage-1 branch** and cite that branch's `.github/workflows/ci.yml`, because jobs moved after the base (the reproducibility install and the alert-routing guard are in `repo-guards`, not `ci-gate-repo`; the benchmark steps are in `benchmark-gate`; `slo-rules-check` and the `ci-gate-repo` evaluation are at :351-369, :3230 and :3253). Every other citation keeps its base-commit line.
- `npx --yes markdownlint-cli2 --no-globs engineering/architecture-v2/34-readiness-audit-addendum-2026-11-13.md engineering/architecture-v2/00-status-and-evidence.md` → 0 problems.
- `bash infra/scripts/agent-docs-check.sh fast` → 0.
- `node site/scripts/check-claims.mjs` → pass (this file is outside the scanned roots).
- `python3 benchmarks/scripts/check_reproducibility.py` → exit 0, 4 warnings, 81 unrecorded runs.
- Not verified: no hosted origin, cluster, PITR run, or p99 measurement was available to this addendum; rows that need one are recorded with their blocker, not scored.
- Staging record: [`35-v1-remaining-gaps-staged-2026-11-13.md`](35-v1-remaining-gaps-staged-2026-11-13.md) classifies every remaining row into four stages with the exit gate and the traceability arithmetic, re-verified at `55a62bc4`.

## 6. Stage 2 pass — recovery and operability

A stage-2 pass closed 15 of the 25 rows in `35-v1-remaining-gaps-staged-2026-11-13.md` §4; §4.1 records each with its evidence. In summary:

- **Readiness and runbooks.** Proxy treats Postgres as critical (`services/proxy/internal/bootstrap/wire.go`:501-506), memory and API readiness check their live dependencies (`services/memory/app/probes.py`:38-75; `services/api/app/probes.py`:34-90), and six missing runbooks now exist under `engineering/runbooks/` with an index entry each.
- **Observability and drills.** The backup-freshness and restore-drill metrics are scraped through a node-exporter textfile collector, the drill seeds a real fixture and computes `rto_pass` against a configurable target, the Tempo assertion is bound to one request's trace id, and Console `/metrics` exists. Context and memory SLIs are recorded with absence alerts; the burn thresholds remain unratified, so this pass records SLIs, not SLOs.
- **Recovery surface.** `make v1-backup`, `make v1-restore` and `make v1-pitr` exist, and a restore-replay test proves a restore carries forget markers and receipts. `pgbackrest-restore.sh` still has no PITR target support, so `make v1-pitr` refuses; a live backup/restore was not run here.

Ten rows remain, each with its blocker in §4.2: `P0-09`, `P0-10`, `P0-11`, `P0-19`, `P1-47`, `P2-12`, `GAP-011`, `O04` (broker decision), `D4`, `D11`.

**One correction worth recording.** The stage-1 migration work (P2-10) tried per-run database isolation and deliberately removed it: the migrations create and drop **cluster-global** roles (`000004`, `000036`, `000064`, `000068`), so a second database holding their grants blocks `DROP ROLE` with SQLSTATE `2BP01`, and the error names that other database (`infra/migrations/postgres/migrate_integration_main_test.go`:14-55). The harness repairs an interrupted predecessor instead (`:63-88,115-135).
