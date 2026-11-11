# v1.0 release plan — re-baselined 2026-11-09

**Title:** From the W3 merge to `v1.0.0`: verified status, wave plan, acceptance evidence, and the decisions that block it.
**Audience:** The maintainer/owner and the IBEX agent team.
**Status:** Plan. It records what is true at `df15390d`, sequences the remaining work, and names the decisions only the owner can take. It promotes no ledger row and closes no gap by itself.

---

## 1. Why this replaces the sequencing in `27-v1-readiness-audit.md` §7

The audit was written at `6f12c96c` (2026-11-05). Two waves have landed since and changed its facts:

- [ADR-0097](../adr/0097-v1-supported-profile.md) selected `v1-single-node`, and PR #1147 built it: a
  fourteen-service Compose profile with an edge TLS terminator, digest-pinned dependencies, a pinned TEI/bge-m3
  backend, a one-shot migration gate, a one-time bootstrap, and a recorded start (`29-v1-single-node-start-record-2026-11-07.md`).
  That closes **P0-01** and **P0-02** *for that profile*, and builds the transport half of **P0-22** (its production
  acceptance is still missing).
- PR #1152 landed W3's first slice: erasure, the org-deletion cascade, the six-table ClickHouse purge, and
  `ibex_app` pinning for **api, mcp-operator and memory** — closing **P0-07**, **P0-08** and the memory/API half of
  **P0-06**.

The audit's wave order (W4 recovery, W5 contracts, …) still holds for what is left, but two things moved: the tenancy
wave is **half done**, not done, and one P0 became a **dated** obligation (`P0-16`: the nine runtime rows were
re-verified on 2026-11-09, and the `idempotency-operation.v1` contract shape lapsed on 2026-11-10 and was renewed by the
owner on 2026-11-11 — [`33-idempotency-shape-lapse-record-2026-11-11.md`](33-idempotency-shape-lapse-record-2026-11-11.md)). A plan that does not
say that would repeat the audit's mistake of scoring the tree from stale evidence.

---

## 2. Verified status at `df15390d` (2026-11-09)

Every row was checked against the tree, not against the previous document.

| P0 | Audit finding | Status today | Evidence checked |
|---|---|---|---|
| P0-01 | No profile serves the critical path | **Closed for `v1-single-node`** | `infra/compose/v1-single-node/compose.yml`: postgres, redis, migrate, bootstrap, auth, proxy, api, memory, embedder, tei, worker, context, console, edge; `make v1-up`; start record |
| P0-02 | Context is undeployable | **Closed for `v1-single-node`** | `services/context/Dockerfile`; `context` runs in the proxy's network namespace and is reached on `127.0.0.1:9092`, so it publishes nothing |
| P0-03 | Kubernetes cannot install or upgrade | **Closed by exclusion (ADR-0097 §10)** | ADR-0097 §10 states it in release-note words: "Kubernetes, Helm and any HA topology; no rolling upgrade; a restart is an outage". The chart README says its values are render/lint scaffolding, not deployable artifacts; the live guard is `.github/scripts/check-helm-deployable.sh` (the audit's filename is stale). No 1.0 claim depends on it |
| P0-04 | Console cannot be logged into | **Open** | no `login`/`logout` page under `services/console/app/pages/`; all BFF routes are reads |
| P0-05 | Cookie sessions cannot mutate | **Open** | `services/console/server` has no cookie-capable mutation path; mutations need a bearer PAT |
| P0-06 | RLS inert / bypass survives pinning | **Partially closed — service-bypass removal in PR-1** | `000063`–`000067` and [ADR-0098](../adr/0098-remove-forgeable-service-bypass.md) remove the forgeable service-account flag, drop `ibex_service`'s `BYPASSRLS`, and create inert capability roles plus per-function readers; **the tenant selector remains `app.current_org_id`, so arbitrary SQL as `ibex_app` can still select another tenant**; `api`, `mcp-operator`, `memory` already pin `ibex_app`; **`auth` repositories pin `ibex_app` and resolve a bearer by prefix through `auth_find_token_by_prefix` as of PR #1172; `auth` bootstrap, `worker`, the relay test fixtures and `packages/session` still set `app.is_service_account` until PR-3..4** |
| P0-07 | Org deletion aborts on the ledger | **Closed** | migrations `000059`–`000062`; `test_org_postgres_purge_clears_idempotency_ledger` |
| P0-08 | Forget does not erase | **Closed** | erase + child deletes + ledger marker; `test_forget_erases_content_and_child_labels`, `test_finalize_after_forget_stores_the_erased_marker` |
| P0-09 | No backup | **Open — and absent from the profile** | no `pgbackrest`/WAL service in `compose.yml`; `infra/backup/pgbackrest` is `.example` only |
| P0-10 | No restore proof | **Open** | the only drill artifact used `pg_dump`; no PITR workflow |
| P0-11 | No RPO/RTO per data class | **Open** | `15-runtime-operations-and-recovery.md` defines the classes, no signed numbers |
| P0-12 | `buf-breaking` advisory | **Open** | `.github/branch-protection-main.json` requires the `ci-gate-*` set; `buf-breaking` is not in it |
| P0-13 | OpenAPI is freshness-checked only | **Open** | no `oasdiff` anywhere in `.github/` or `infra/scripts/` |
| P0-14 | Contract registry covers 5 of 75 routes | **Open** | no registry-completeness check in CI |
| P0-15 | Release pipeline blocked | **Open — owner action** | `.version-release-manifest.json` = `0.1.9`; 121 commits since `v0.1.9`; `release.yml`/`release-docker.yml` require `VERSION_RELEASE_TOKEN`; #1068 |
| P0-16 | Provisional rows expire 2026-11-10 | **Closed by owner decision 2026-11-11 — the lapse item only** | the nine runtime rows read `2027-02-06` with their suites re-run at `df15390d` (`32-ledger-review-2026-11-09.md`). The `idempotency-operation.v1` **contract shape** lapsed on 2026-11-10 with no decision recorded, and the owner renewed it to 2027-02-06 on 2026-11-11 on that §4 packet plus the additive `409 IDEMPOTENCY_KEY_ERASED` term (PR #1152) ([`33-idempotency-shape-lapse-record-2026-11-11.md`](33-idempotency-shape-lapse-record-2026-11-11.md)). Closing this row clears the expired claims only: it certifies no runtime row's own GAP criterion, and GAP-004's measurement requirement stays open in `18-gap-register.md` |
| P0-17 | The supported profile is unselected (D5) | **Closed at the decision level** | ADR-0097 selects `v1-single-node` and §10 states the exclusions; the profile now starts (`29-v1-single-node-start-record-2026-11-07.md`). The remaining acceptance evidence is tracked by P0-01 and P0-22, not by this row |
| P0-20 | Published latency is not reproducible | **Open** | the HNSW artifact carries no runner CPU/RAM, and `baseline-modes.json` records a run URL but no commit, gold-set hash or seed; the gate compares corpus names. W10.1 closes it |
| P0-18 | Exception text reaches spans and logs | **Closed** | `services/worker/app/observability.py:95-111` starts the span with `record_exception=False` and sets only the exception type name; `services/api/app/errors.py:188-198` logs type, `request_id` and frame `file:line` only, never the message; sentinel tests cover both — `services/worker/tests/unit/test_traced_task.py:48-69` and `services/api/tests/unit/test_error_handlers.py:151-159` |
| P0-19 | Nothing pages | **Open** | `infra/monitoring/alertmanager/alertmanager.yml` routes to `local-null` |
| P0-21 | No route-level two-tenant acceptance | **Partially closed** | tenant negatives exist for org/user, agent and token management; no negative for the operator read routes and no two-tenant browser journey |
| P0-22 | Chat path cannot authenticate outside development | **Open — transport built, production acceptance missing** | the profile carries per-install TLS on every hop (`IBEX_AUTH_GRPC_TLS_*`, `IBEX_AUTH_GRPC_CA_FILE` on proxy/api/memory; edge only port published), but the recorded start is `IBEX_ENV=staging` with `IBEX_LLM_MODE=mock` (`29-v1-single-node-start-record-2026-11-07.md`). No start on `IBEX_ENV=production` has served an authenticated chat request, which is the row's own acceptance evidence |

**One-line verdict:** the profile is real, erasure is real, tenancy is **half** real, and the three things that make a
1.0 defensible — recovery, contract gates, release integrity — are untouched. Nine ledger rows lapse tomorrow.

---

## 3. The bar (unchanged)

A 1.0 claim needs: one deployable profile; stable contracts with a deprecation window; provable tenancy and erasure;
recoverability with a stated RPO/RTO; observability that pages; a usable operator product (or a declared read-only
scope); reproducible quality and release artifacts; and claims that match the evidence. Nothing in this plan lowers
that bar; several items below exist because the bar is high.

---

## 4. Waves and exit gates

Order is chosen to remove risk before polish, and to avoid rework: recovery and tenancy are independent of the product
surface, contracts are mechanical, and the release wave needs the owner's secret last.

### W0 — truth and scope (today, 2026-11-09)

| # | Work | Acceptance evidence |
|---|---|---|
| 0.1 | Resolve the nine rows that expire 2026-11-10 | **Done.** Every row was re-verified at `df15390d` by running its own evidence suite and re-dated to 2027-02-06 with status and limitations unchanged — see [`32-ledger-review-2026-11-09.md`](32-ledger-review-2026-11-09.md) §2. The `idempotency-operation.v1` **contract shape** was the one act that review could not perform; it then lapsed on 2026-11-10 and the owner renewed it on 2026-11-11 (P0-16, [`33-idempotency-shape-lapse-record-2026-11-11.md`](33-idempotency-shape-lapse-record-2026-11-11.md)) |
| 0.2 | Point P0-03 at the exclusion and record the chart's status | **Done.** ADR-0097 §10 already excludes "Kubernetes, Helm and any HA topology" in release-note words; the chart README calls its values render/lint scaffolding; the live guard is `check-helm-deployable.sh` |
| 0.3 | Land the two carried-over items | **Landing.** The plan-gate determinism fix passes three consecutive runs (4m13s / 4m11s / 4m59s) and the ledger-scope unit coverage brings `ledger_scope.py`, `db.py` and `erased_response.py` to 100%; both are in PR #1164 |

**Gate:** no ledger row past its date (**met for runtime rows**); the contract shape renewed or downgraded by the owner
(**open**); P0-03 cited to ADR-0097 (**met**); CI free of the known flake (**met, pending the merge of #1164**).

### W4 — recovery (the largest residual risk)

| # | Work | Acceptance evidence |
|---|---|---|
| 4.1 | Add a backup service to `v1-single-node`: pgBackRest with a repository **outside the host failure domain** (S3/MinIO or an external POSIX target), WAL archiving on, `archive_timeout` set, schedule + retention. A host-local volume may cache the repository but cannot be the only copy | `compose.yml` starts the backup service against the off-host repository; `pgbackrest check` green; a scheduled backup exists **and a restore from the off-host copy succeeds** |
| 4.2 | Alert on archive lag and backup freshness (feeds W6) | rule + alert firing on an induced archive failure |
| 4.3 | Restore drill: full restore **and** PITR to a timestamp, from the off-host repository, measured against the signed targets | `restore-drill` record with `rto_pass` computed against the signed RTO (not merely measured), `rpo_pass=true`, target commit, post-restore isolation assertions, **and a restored provider credential decrypts with the recovered `IBEX_CREDENTIALS_MASTER_KEY`** |
| 4.4 | Sign the RPO/RTO table per data class (Postgres canonical, outbox, object artifacts, Redis projections, vector index) | table in `15-runtime-operations-and-recovery.md` with numbers, owner and date, referenced from the profile page |
| 4.5 | Back up `IBEX_CREDENTIALS_MASTER_KEY` (and its ID) separately from the database and prove a restored provider credential decrypts | the drill starts a restored stack and reads one provider credential through the API; without the key the auth config refuses to start in production (`services/auth/internal/config/config.go:249`) |
| 4.6 | Provide a `make v1-restore` / `v1-backup` operator path | one command each, documented, exercised by 4.3 |

**Gate:** one green PITR drill per release with measured RPO/RTO, and the numbers published in the profile page.
**Research basis:** pgBackRest's POSIX-repo configuration, `archive_mode`/`archive_command`/`archive_timeout`, stanza
init/check/backup and `--type=time --target=… --target-action=promote --delta` restore are the shape used here; the
same source warns that a persistent archive failure grows `pg_wal` until the disk fills, which is why 4.2 exists.
([pgBackRest configuration reference](https://pgbackrest.org/configuration.html),
[PITR with pgBackRest in Docker](https://dataegret.com/2025/12/pgbackrest-pitr-in-docker-a-simple-demo/))

### W8 — tenancy completion (was half of W3)

**Sequencing:** 8.0 is the database foundation and lands first (PR-1). 8.1–8.3 are the service pinning (PR-2..4). No
login or DSN swap happens before the matching service pin: until a service pins its role it still connects as the owner
login, so the policy change is inert for that path rather than silently bypassed.

| # | Work | Acceptance evidence |
|---|---|---|
| 8.0 | Land the policy foundation: `current_user = 'ibex_service'` predicates, `ibex_service NOBYPASSRLS`, the four capability roles, the five `SECURITY DEFINER` readers, password/limit provisioning, and the token-prefix index (**PR-1**) | migrations `000063`–`000067`; [ADR-0098](../adr/0098-remove-forgeable-service-bypass.md); `tenancy_*_integration_test.go` A1–A3/A7, sealed purge reads, the legal-hold trigger, provisioning, and the down/up cycle are green |
| 8.1 | Pin `ibex_app` in `services/auth` repositories and `bootstrap`; move the token lookup to `auth_find_token_by_prefix` and remove the bypass from every production path | statement-capture test per repository: `SET LOCAL ROLE ibex_app` present, `app.is_service_account` absent; reader called as `ibex_runtime` |
| 8.2 | Pin `ibex_app` in `services/worker` (extraction, budget, idempotency facade) | worker integration test with RLS enforced and no bypass; an unfiltered `SELECT` returns one tenant |
| 8.3 | Pin the Go `packages/session` / `packages/directive` / `packages/modelpolicy` / `packages/budgetledger` stores, or move the purge-only paths to `ibex_service` | `-tags=integration` RLS tests per package; `ibex_service` used only where cross-tenant reach is the point |
| 8.4 | Route-level cross-tenant negatives for the operator read routes (`/v1/operator/agents`, `/v1/operator/context`, `/v1/operator/platform/health`) and the memory/proxy chat path | one negative per path, asserting 404 not 403 |
| 8.5 | Two-tenant browser journey against `v1-single-node` | Playwright run with two orgs, no fixture cookie, assertions on isolation in the Console BFF |

**Gate:** the cross-tenant negative suite is green **in the supported profile**, with the bypass unavailable, and no
production path sets it.

### W5 — contracts and compatibility

| # | Work | Acceptance evidence |
|---|---|---|
| 5.1 | Make `buf-breaking` a required check; prove it with a deliberately breaking PR | branch-protection update + red-then-green evidence |
| 5.2 | Add `oasdiff breaking` against a pinned baseline (`origin/main` and the release tag), `fail-on: WARN`, `review: false` so no spec leaves CI | a deliberately breaking `/v1` change fails; an additive change passes |
| 5.3 | Generate the contract registry from `route_inventory.json`, the proto files and the MCP descriptors; fail CI on an unregistered surface | registry diff empty; a new unregistered route fails the check |
| 5.4 | Deprecation policy in code and docs: `Deprecation`/`Sunset` headers, beta 31 days / stable 180 days, and the support window; the same policy text covers REST, gRPC **and MCP tool schemas** | oasdiff deprecation checks green; a removal before its window fails CI; `16-compatibility-and-versioning.md` states the window for all three surfaces |
| 5.5 | MCP descriptor diff in review: the committed descriptor is compared with the previous one, and a schema change carries a recorded deprecation decision (notice date, stability class, removal date) rather than only a hash change | a changed tool schema shows a readable diff and its deprecation record; a removal without that record fails the check |

**Research basis:** oasdiff's `breaking` command, `fail-on: WARN`, git-revision specs (`origin/main:openapi.json`) and
the `deprecation-days-beta` / `deprecation-days-stable` defaults are the parameters used above.
([oasdiff action](https://github.com/oasdiff/oasdiff-action), [git revisions](https://github.com/oasdiff/oasdiff/blob/main/docs/GIT-REVISION.md))

### W6 — observability that pages

| # | Work | Acceptance evidence |
|---|---|---|
| 6.1 | Stop exception text reaching spans and logs: worker `record_exception=False` honoured, API logs redacted | sentinel-exception tests: the sentinel is absent from exported spans and captured logs |
| 6.2 | Real Alertmanager receiver (webhook) + one delivered test alert; rule map to `14-failure-modes-and-readiness.md` | screenshot/record of the delivered alert and the rule-to-failure-mode table |
| 6.3 | SLOs and burn-rate alerts for proxy overhead, context assembly and memory retrieval | rules present; one synthetic burn fires |
| 6.4 | `context` `/metrics`; scrape api, relay, console; assert one OTel→Tempo trace end to end | metrics target `UP`; a trace id found in Tempo for a known request |

**Gate:** a synthetic alert reaches a human, and one trace is asserted end to end.

### W7 — release integrity

| # | Work | Acceptance evidence |
|---|---|---|
| 7.1 | Owner sets `VERSION_RELEASE_TOKEN`; the Version Release workflow runs green | run URL; release PR opened by the pipeline |
| 7.2 | Signed annotated tags; tag protection | `git cat-file -t vX` = `tag`, `git tag -v` verifies |
| 7.3 | Manifest schema-validated and signed **at upload**; per-image SBOM; `cosign verify` in the pipeline | a release whose manifest and images verify |
| 7.4 | Reproducible builds: remove `apt-get upgrade` from memory/embedder; record base digests | two builds of the same commit produce the same digest |
| 7.5 | Bundle smoke on the tag, and the v1 profile smoke in CI | `v1-smoke` job green on the tag |

**Gate:** cut `v0.2.0` entirely through the pipeline, then repeat for `1.0`.

### W9 — operator product

| # | Work | Acceptance evidence |
|---|---|---|
| 9.1 | Login / refresh / logout pages and BFF routes with httpOnly cookies | clean-browser Playwright: login → live page → refresh → logout, no fixture cookie |
| 9.2 | Cookie-capable mutations with CSRF (double-submit) and step-up where needed — **or** a declared read-only 1.0 (decision D-C) | mutation journey green, or the scope statement + UI that cannot lie about it |
| 9.3 | Tenant provisioning route | an org created through the API and visible in the Console |
| 9.4 | All ten core surfaces live, or the preview ones removed from navigation and the ledger | surface inventory matches `surfaces.ts`; claims check green |

### W10 — quality evidence and honest claims

| # | Work | Acceptance evidence |
|---|---|---|
| 10.1 | Reproducible ranking baseline: runner profile in the HNSW artifact, `sha` + gold-set hash + seed in the baseline, gate rejects mismatch | re-running the published numbers from the commit reproduces them |
| 10.2 | Publish v2 ranking modes; fix `full_graph == hybrid_rerank`; gate `graph_mode_distinguished` | site data matches the artifact; the gate fails on a regression |
| 10.3 | Model inventory (model, revision, licence, fallback) and embedding-version filtering + re-embed runbook (also #1153's recall test) | inventory committed; a search filtered by `embedding_model` |
| 10.4 | Injection-risk classifier/quarantine, and the "data, not instructions" framing on memory-only assemblies | injection-shaped memory is quarantined; formatter test |
| 10.5 | Claims pass: README "evidence on every request", proxy p99, Console counts, `API_DOCUMENTATION.md` | every public sentence has a ledger row or is reworded |

---

## 5. Decisions only the owner can take

| ID | Decision | Why it blocks | Default if silent |
|---|---|---|---|
| D-A | `VERSION_RELEASE_TOKEN` and the tag-signing key | W7 cannot start; 121 commits are unreleased | no 1.0 tag |
| D-B | Confirm ADR-0097 §10 is the final word on Kubernetes/Helm for 1.0 (already stated there) | it is recorded, but the chart still exists and needs a stated fate | the row stays cited to §10 and the chart is marked non-shipping |
| D-C | Console 1.0: login + mutations, or login + declared read-only | changes W9 by roughly a week and changes P0-05's acceptance | read-only, stated |
| D-D | Which **off-host** backup repository `v1-single-node` requires (S3/MinIO or an external POSIX target) and the RPO/RTO to sign | a host-local repository cannot survive host loss, so its choice is a release decision, not a default | S3/MinIO if available, else an external POSIX target; RPO ≤ 5 min, RTO ≤ 60 min, both drill-measured |
| D-E | `idempotency-operation.v1`: renew the contract shape to 2027-02-06 on the evidence packet in `32-ledger-review-2026-11-09.md` §4, or downgrade it | **Decided 2026-11-11: renewed to 2027-02-06** on that packet plus the additive `409 IDEMPOTENCY_KEY_ERASED` term (the shape had lapsed 2026-11-10; P0-16) | the ledger and registry record the renewed review date |
| D-F | Confirm hosted/HA stays out of 1.0 and approve the reworded claims | P1-51/52 and the README | reword to what is measured |

---

## 6. v1.0 definition of done

A tag is defensible only when every line below has a linked artifact:

- [ ] `make v1-up` on a clean host reaches healthy on every service, and `make v1-smoke` passes against it.
- [ ] The profile serves one authenticated chat request on `IBEX_ENV=production` (the staging + mock start is not that
      evidence).
- [ ] Backup runs on a schedule to a repository **outside the host failure domain**; a PITR drill restores from it to
      a timestamp with `rpo_pass=true` and an RTO measured against the signed target.
- [ ] A restored provider credential decrypts with the recovered `IBEX_CREDENTIALS_MASTER_KEY`; the key has its own
      backup and recovery step.
- [ ] The cross-tenant negative suite is green in the profile **with the service-account bypass unavailable**, at the
      route level, plus the two-tenant browser journey.
- [ ] A forget erases content, child rows and the idempotent response; a restore replays markers and receipts.
- [ ] `buf-breaking` and `oasdiff breaking` are required checks and both fail on a deliberately breaking change; the
      registry lists every shipped route, gRPC method and MCP tool.
- [ ] One alert reaches a human; one trace is asserted end to end.
- [ ] The release is produced by the pipeline from a signed tag with a signed manifest and per-image SBOMs that verify.
- [ ] Published numbers reproduce from the tagged commit; every public claim matches a ledger row.
- [ ] The Console journey works in a clean browser, or the read-only scope is declared in the ledger and the UI.

---

## 7. Risks and how they are retired

| Risk | Retirement |
|---|---|
| Restore drill passes on paper only | W4 makes the drill the exit gate, not the backup |
| Host loss destroys the database and its backup together | the repository is off-host by contract (W4.1); a restore from it is the drill |
| A restore cannot decrypt provider credentials | the master key has its own backup and a decryption check in the drill (W4.3) |
| Pinning roles breaks auth/worker/proxy under load | one service per change, with its integration suite and a cross-tenant negative |
| `oasdiff` drowns the team in warnings | start `fail-on: WARN` with an ignore file, review it quarterly |
| Console auth inherits CSRF holes | double-submit CSRF + Playwright journey, reviewed by security |
| Release integrity ships unverified signatures | `cosign verify` is in the pipeline, not a manual step |
| Claims drift again after 1.0 | the claims check stays a required gate, and the ledger review date is enforced |

---

## 8. What starts now

W0 is cheap, dated, and unblocks everything: resolve the nine rows, write the Kubernetes exclusion, land the two
carried-over PRs. W4 starts next because data loss is the only risk that cannot be fixed after a release.

The plan changes no status. Every wave closes its rows only when its acceptance evidence exists.
