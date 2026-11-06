# v1.0 Readiness Audit

**Title:** What must be fixed before IBEX Harness can honestly ship `v1.0.0`.
**Description:** A domain-by-domain audit of architecture, security, data, AI/retrieval, product and operations at `6f12c96c`, merged into one prioritised gate list. It records what blocks 1.0, what should ship with it, and what may ship as a documented limitation.
**Audience:** The maintainer/owner, the IBEX agent team, and any reviewer asked to approve a 1.0 tag.
**Status:** Audit input only. It changes no status, closes no gap, and authorises no runtime work. **Amended 2026-11-06 at `b400070f`:** P0-22 added (surfaced by the profile review), P0-17 closed at the decision level by ADR-0097, P1-04 and P1-05 corrected against the tree, §6 updated. The two amendments change no status value and run no runtime work; they correct the record.
**Base:** `main` at `6f12c96c` (2026-11-05). **Method:** six independent read-only domain audits, then a lead merge.

## 1. The bar this document applies

`engineering/RELEASING.md` says it plainly: **"`v1.0.0` only after explicit production-readiness and compatibility sign-off."** The ledger's claim rule then requires a 1.0 claim to carry a source commit, an evidence artifact, a deployment profile, an owner and a review date, and forbids `complete`/`supported`/`production-ready` without one.

So 1.0 means, concretely:

1. **A selected, deployable profile.** One documented way to run the product that actually serves the documented critical path, with pinned versions, health checks, an upgrade path and a rollback.
2. **Stable contracts.** REST, gRPC and MCP surfaces that cannot break silently, with a deprecation window.
3. **Provable tenancy and erasure.** Every data path fails closed, and deletion can be demonstrated.
4. **Recoverability.** Backups that run, a restore that is drilled, and an RPO/RTO that is stated.
5. **Observability that pages.** Alerts reach a human; SLOs exist with error budgets.
6. **A usable operator product.** The Console can actually be logged into and managed, or 1.0 says read-only.
7. **Reproducible quality and release artifacts.** Published numbers and images can be traced to a commit and rebuilt.
8. **Honest claims.** Every public sentence matches the evidence.

## 2. Verdict

**Not ready for 1.0.** The audit found **22 P0 rows; 21 remain open**. P0-17 (D5, the unselected profile) was
discharged at the decision level on 2026-11-06 by
[ADR-0097](../adr/0097-v1-supported-profile.md) and the [G0 review record](28-g0-review-record-2026-11-06.md); that
closes the decision, not the profile. The two that dominate everything else:

- **There is no deployable profile that serves the product.** `memory-context` is data-plane only; `services/context` has no Dockerfile at all; the Console has no image; the Helm chart self-declares as lint scaffolding with sentinel digests; and the documented critical path spans services that no single profile starts.
- **Tenant isolation is not enforced at the database for most services, and the bypass survives role pinning.** Memory, worker, proxy and the shared Go packages set the org GUC but connect as the superuser `ibex`, so RLS never applies; only the API and mcp-operator pin `ibex_app`. And `set_service_org` sets `app.is_service_account='true'` on every memory read and write, which the RLS policy treats as "allow every row" — so pinning the role alone does not produce cross-tenant isolation.

A third, on a timer — now partly defused, not resolved: **the packet no longer wholly expires on 2026-11-10**. The
2026-11-06 review re-verified the four `accepted` contract shapes with new evidence and moved only those rows to
2027-02-06. Every `provisional` runtime row still expires 2026-11-10 and is re-verified by the wave that owns it, because
re-dating those before the profile runs would be a promotion in disguise.

## 3. P0 — blocks 1.0

A 1.0 claim would be false, unsafe, or undeliverable without these.

### 3.1 Deliverability

| ID | Owner role | Finding | Evidence | Acceptance evidence |
|---|---|---|---|---|
| P0-01 | ibex-sre + ibex-architect | **No profile serves the critical path.** The only supported bundle is memory substrate; context has no image; app services are host-run in dev compose. | `infra/compose/bundles/memory-context.yml`; `services/*/Dockerfile` (8 of 11); `infra/compose/dev/docker-compose.yml:2-111` | One named profile with proxy + auth + api + memory + context + embedder (+ worker/console), containerised, started by one command, healthy |
| P0-02 | ibex-platform-engineer + ibex-security | **Context assembly is not deployable.** No Dockerfile, compose service, Helm template, or publish job; the server refuses non-loopback binds, so it cannot run as a networked service. | `services/context/app/server.py:5,147,155`; `.github/workflows/docker-publish.yml` (7 images, no context) | Context image + profile entry + a decided transport (TLS or documented mesh boundary) |
| P0-03 | ibex-sre | **Kubernetes profile cannot install or upgrade.** Sentinel digests, missing datastore templates, migrate image unpublished and disabled. | `infra/helm/ibex-harness/values-prod.yaml:4-6,17-24`; `check-helm-digest-placeholders.sh` fails today | Guard exit 0; one clean install and one upgrade on a disposable cluster, or Kubernetes declared out of 1.0 scope |
| P0-04 | ibex-platform-engineer | **The Console cannot be logged into.** No login/refresh/logout page or BFF route; the UI has a "Sign in" state and no way out of it; e2e bypasses auth with a fixture cookie. | no login page under `services/console/app/pages/`; all BFF routes are `*.get.ts`; `services/console/e2e/live-stack.mjs:49-53` | Clean-cookie Playwright: login → live page → refresh → logout, no test bypass |
| P0-05 | ibex-platform-engineer + ibex-security | **Cookie sessions cannot mutate.** Management writes require a bearer PAT; the BFF forwards only the cookie, so agents/tokens/users/settings are unreachable from the Console by design. | `services/api/app/authz.py:76-94`; `services/console/server/utils/operator/http.ts:130-164` | Cookie + CSRF/step-up capable authorization, or an explicit read-only 1.0 scope |
| P0-22 | ibex-go-systems + ibex-security | **The chat path cannot authenticate outside `development`.** Diagnosed per hop. **proxy → AuthService:** the proxy dials TLS for every `IBEX_ENV` except `development`/empty (`authTransportCredentials`), but AuthService registers no server transport credentials, so this hop always fails outside `development` — and every chat request needs it. **API → AuthService:** plaintext on both sides (`grpc.aio.insecure_channel` behind `assert_trusted_insecure_auth_target`), so it works over a Compose short name but with no transport security. **browser → Console BFF → API:** the BFF refuses to send a session cookie to a non-HTTPS API origin, and nothing in the Compose path terminates TLS. | `services/auth/cmd/auth/main.go` (`newAuthGRPCServer`); `services/proxy/internal/bootstrap` (`authTransportCredentials`); `services/api/app/auth/session_refresh.py:79,181,210`; `packages/authclient/src/authclient/target.py`; `services/console/server/utils/operator/http.ts` (`fetchOperatorJson`); the only ingress `tls:` declaration is the Helm scaffold (`infra/helm/ibex-harness/templates/api-ingress.yaml`), which needs an operator-supplied secret and belongs to the excluded Kubernetes path; the OTel collector configs carry outbound TLS settings, not an inbound terminator | One transport per hop, TLS or co-located loopback, decided in ADR-0097; a start on `IBEX_ENV=production` that serves one authenticated chat request; negative tests for an unauthenticated gRPC client and an unpublished port |

### 3.2 Tenancy and data safety

| ID | Owner role | Finding | Evidence | Acceptance evidence |
|---|---|---|---|---|
| P0-06 | ibex-platform-engineer + ibex-data-engineer | **RLS is inert, and the service-account GUC bypasses it even when the role is pinned.** Memory, worker, proxy and the Go packages set the org GUC but connect as superuser `ibex`; and `set_service_org` sets `app.is_service_account='true'` on every memory read and write, which `rls_org_visible` treats as "allow every row". Pinning `ibex_app` alone does not close cross-tenant access. | `services/memory/app/db.py:50`; `services/memory/app/org_context.py:13-22`; `000004_rls.up.sql:10,22`; `000009_create_directives.up.sql:104-118`; catalog `rolsuper=t` | Every service session pins a non-superuser role; the bypass is removed or restricted to a role the tenant-facing connection cannot assume; a cross-tenant test runs through each real session factory **with the bypass unavailable** |
| P0-07 | ibex-data-engineer | **Org deletion aborts on the idempotency ledger.** `idempotency_ledger.agent_id` is `NO ACTION` and the saga deletes agents first. | `000043_idempotency_ledger.up.sql:4-5`; `services/worker/app/tasks/org_deletion.py:104-134` | Seeded org with ledger/budget/evidence rows reaches `succeeded`, zero rows remain |
| P0-08 | ibex-memory-intelligence | **Forget is a visibility tombstone, not erasure.** It nulls embedding fields but keeps `content`; the lifecycle outbox has no consumer. | `services/memory/app/lifecycle.py:107-122` | Forget (or a receipted purge) removes content; test asserts the text is gone and a per-memory receipt exists |
| P0-09 | ibex-sre | **No backup exists.** `backup.enabled` renders nothing, no WAL archive, pgBackRest is `.example` only; nothing schedules a backup. | `infra/helm/ibex-harness/values.yaml:69-78`; `infra/backup/pgbackrest/pgbackrest.conf.example`; `infra/scripts/platform/pgbackrest-backup.sh:19-27` | Shipped schedule + WAL archive; freshness alert fires and clears |
| P0-10 | ibex-sre | **No restore proof.** The committed drill used `pg_dump`, not PITR: `rpo_pass=false`, ClickHouse unreachable; no workflow runs a drill. | `infra/scripts/platform/evidence/4p5-restore-drill/restore-drill-report.json` | One green PITR drill per release, measured RPO/RTO, post-restore isolation assertions |
| P0-11 | ibex-sre + owner | **No RPO/RTO is defined per data class.** Numbers live in script constants; G8 has no acceptance threshold. | `15-runtime-operations-and-recovery.md:1-20`; `restore-drill.sh:38-44` | Signed objective table per store, referenced from `DEPLOYMENT.md` |

### 3.3 Contracts and release integrity

| ID | Owner role | Finding | Evidence | Acceptance evidence |
|---|---|---|---|---|
| P0-12 | ibex-go-systems | **`buf-breaking` is advisory.** Protobuf is the only shared wire contract; a tag reuse merges green. | `.github/workflows/ci.yml:315-320` | Required check; a deliberately breaking PR proves red |
| P0-13 | ibex-platform-engineer | **The OpenAPI snapshot is freshness-checked, not breaking-checked.** Regenerating it in the same PR legalises any `/v1` change across 75 routes. | `.github/scripts/check-openapi-snapshot.sh:9-16` | `oasdiff`-style breaking gate against a pinned release baseline |
| P0-14 | ibex-architect | **GAP-003: the contract registry covers 5 shapes while 75 REST routes, 3 gRPC services and 8 MCP tools ship.** A compatibility policy cannot bind unregistered surfaces. | `18-gap-register.md:9`; `03-contract-registry.md:120-186`; `route_inventory.json` | Registry complete with owner/version/compat class; CI fails on an unregistered route or tool |
| P0-15 | owner | **The release pipeline is blocked.** `VERSION_RELEASE_TOKEN` is unset; no release since v0.1.9 (2026-10-04) across 93 commits. | `version-release-pr.yml:51-56`; `release.yml:38-46`; `.version-release-manifest.json` | Green Version Release run → release PR → signed tag |
| P0-16 | owner | **The `provisional` runtime rows still expire 2026-11-10.** The 2026-11-06 review renewed only the four `accepted` contract shapes; a 1.0 sign-off that cites any runtime row after that date rests on a lapsed claim. | `00-status-and-evidence.md:3` and its "When a claim expires" rule; `28-g0-review-record-2026-11-06.md` §4 | Each runtime row re-verified under the selected profile by the wave that owns it, or downgraded per the ledger rule |
| P0-17 | owner | **The supported profile is unselected (D5).** Every registry row says "Profile not selected", so no certification gate applies. **Closed at the decision level 2026-11-06** by ADR-0097; the profile itself is still not startable (P0-01, P0-02, P0-22). | `26-g0-review-packet.md:134`; `03-contract-registry.md:129,139,149,169,179`; `adr/0097-v1-supported-profile.md` | ~~Signed decision naming one profile and its exclusions~~ — satisfied by ADR-0097; remaining work is acceptance evidence, not a decision |

### 3.4 Security and observability

| ID | Owner role | Finding | Evidence | Acceptance evidence |
|---|---|---|---|---|
| P0-18 | ibex-builder + ibex-security | **Exception text reaches spans and logs.** Worker spans call `record_exception` despite `record_exception=False` at creation; the API logs `exc_info` with no redaction, and a `DBAPIError` traceback carries SQL plus bound parameters. | `services/worker/app/observability.py:93-113`; `services/api/app/errors.py:173-179`; `services/api/app/logutil.py:20-32` | Sentinel-exception tests: sentinel absent from exported spans and captured logs |
| P0-19 | ibex-sre | **Nothing pages.** Alertmanager routes every alert to `local-null`; rules cover 11 of the documented failure modes. | `infra/monitoring/alertmanager/alertmanager.yml:1-11`; `infra/monitoring/prometheus/rules/*.yml` | Real receiver + one delivered test alert + rule map to `14-failure-modes-and-readiness.md` |
| P0-20 | ibex-sre + ibex-memory-intelligence | **Published latency is not reproducible.** HNSW p50/p95/p99 carry no runner CPU/RAM in the artifact; the ranking baseline records a run URL but no commit/digest/seed, and the gate compares corpus *names*. | `site/public/benchmarks/hnsw-benchmark-data.json`; `baseline-modes.json:18-26`; `check_mode_gate.py:147-166` | Runner profile in the HNSW schema; baseline records `sha`, `gold_set_sha256`, seed; gate rejects mismatch |
| P0-21 | ibex-qa | **No end-to-end two-tenant acceptance exists.** The D1 read model and agent projection are tenant-scoped at the service layer (`test_operator_overview_rls.py:193-291`), but there is no HTTP-route-level negative test for `/v1/operator/agents`, `/v1/operator/context` or `/v1/operator/platform/health`, and no browser two-tenant evidence for the Console BFF. | ledger Console row; `services/api/tests/integration/test_operator_overview_rls.py:193-291`; `services/console/server/utils/operator/http.ts:130-172` | One negative cross-tenant test per shipped data path in the selected profile, at the route level, plus a two-tenant browser journey |

## 4. P1 — should ship with 1.0

| ID | Owner role | Domain | Finding | Evidence |
|---|---|---|---|---|
| P1-01 | ibex-architect | Contracts | No deprecation/upgrade policy in code: no `Deprecation`/`Sunset` headers, no support window. | `16-compatibility-and-versioning.md:3-17` |
| P1-02 | ibex-platform-engineer | Contracts | MCP descriptor hash is runtime-computed and self-consistent-only, so schema changes are invisible in review. | `packages/mcp_gateway/src/mcp_gateway/registry.py:142-146` |
| P1-03 | ibex-architect | Contracts | ADR-0084 status contradicts the ledger; ADR-0092–0095 remain `Proposed` while their code paths are live. | `adr/0084…:11`; `adr/0092…0095:15` |
| P1-04 | ibex-sre | Ops | The dependency matrix still disagrees across artifacts. pgvector is a mutable `:pg16` tag in dev compose and the site, but a 0.8.6 digest in the bundle and CI, with a sandbox run recorded on 0.8.7. Redis is `redis-stack:7.4.0-v1` in dev/test, `redis:7.4.2` under a sentinel digest in Helm, and 7.0.15 in the sandbox record. TEI has no pinned image or model anywhere. The ClickHouse doc drift (23.x in `TECH_STACK.md`) is corrected by the 2026-11-06 amendment; the remaining ClickHouse issue is the sentinel Helm digest under the excluded Kubernetes profile. ADR-0097 §8 fixes the supported pins for the Compose profile; the docs and dev artifacts still have to follow. | `infra/compose/dev/docker-compose.yml:3,21`; `site/content/docs/12.deployment/01.docker-compose.md:29`; `infra/compose/bundles/memory-context.yml:9`; `infra/helm/ibex-harness/values.yaml:17-18`; `infra/reference/tei-embeddings.compose.yaml:1-20` |
| P1-05 | ibex-memory-intelligence | Ops | Embeddings are not shippable for a semantic claim. The schema requires `vector(1024)` with `embedding_dim = 1024`; the bundle meets that by forcing `IBEX_EMBEDDING_PROFILE=cpu` with `IBEX_EMBEDDING_DIM=1024`, so the stub writes schema-valid vectors of arbitrary geometry. Writes succeed and search returns something, which is why this is easy to miss. TEI has no image or model pin in any profile. ADR-0097 requires TEI/bge-m3 for `v1-single-node`; the pin is still missing. | `infra/migrations/postgres/000017_memory_schema_v2_expand.up.sql:13,27-36`; `infra/compose/bundles/memory-context.yml:70-71`; `services/embedder/app/config.py:155-166`; `infra/bundles/memory-context.json:16`; `infra/reference/tei-embeddings.compose.yaml` |
| P1-06 | ibex-sre | Ops | Python `/ready` is startup-only for memory; embedder/reranker/Redis never appear in readiness. | `services/memory/app/probes.py:20`; `services/api/app/probes.py:30-38` |
| P1-07 | owner | Release | Release tags are lightweight and unsigned; no tag protection. | `git cat-file -t v0.1.9` → `commit` |
| P1-08 | ibex-sre | Release | The published release manifest is neither schema-validated nor signed **at upload time**: `release-manifest.schema.json` is exercised by `test_manifest_matches_the_published_schema`, but `release-docker.yml` never runs it, and the uploaded file carries no signature. | `release-docker.yml:78-103`; `infra/scripts/test_release_manifest.py`; `infra/release-manifest.schema.json` |
| P1-09 | ibex-sre | Release | No per-image SBOM; the only SBOM is a source-tree scan; signatures/attestations are produced and never verified. | `release.yml:78-110`; no `cosign verify` in any workflow |
| P1-10 | ibex-platform-engineer | Release | Memory/embedder run `apt-get upgrade` at build time, so the same commit rebuilds to a different digest. | `services/memory/Dockerfile:50-52`; `services/embedder/Dockerfile:53-55` |
| P1-11 | ibex-sre | Release | Bundle smoke never runs in CI; the manifest always reports `unverified`. | `Makefile:87-88`; `ci.yml:92` |
| P1-12 | ibex-platform-engineer | Security | `BILLING_READ` is defined but unenforced; rate cards and budget periods are readable by any org token. | `services/api/app/routers/billing.py:56-61`; `permissions_codec.py:25` |
| P1-13 | ibex-builder | Security | `GET …/legal-holds` is authentication-only while mutation needs `LEGAL_HOLD_MANAGE`. | `routers/legal_holds.py:31-38` |
| P1-14 | ibex-platform-engineer | Security | `mcp-memory` hard-codes `allowed_hosts=[]` with protection on, so production MCP requests are rejected 421. | `services/mcp-memory/app/server.py:257-272` |
| P1-15 | ibex-platform-engineer + ibex-security | Security | Auth gRPC is plaintext on `0.0.0.0` while the Go proxy dials TLS outside development — no working transport for a protected profile. | `services/auth/cmd/auth/main.go:393-408`; `services/proxy/internal/bootstrap/redis.go:157-163` |
| P1-16 | ibex-platform-engineer | Security | OTLP export is cleartext unconditionally (worker `insecure=True`, Go `WithInsecure`). | `services/worker/app/telemetry.py:73`; `packages/telemetry/exporter.go:19-22` |
| P1-17 | ibex-sre + ibex-security | Security | No rotation mechanism for service tokens; `DEPLOYMENT.md` claims 24 h overlap that the code does not implement. | `DEPLOYMENT.md:348-352` vs `adr/0096…:106-107` |
| P1-18 | ibex-security | Security | `osv-scanner.toml` ignores a nitro-server advisory absent from the waiver table; the "Console is not hosted" reason does not cover self-hosting. | `osv-scanner.toml`; `DEPENDENCIES.md:408-419` |
| P1-20 | ibex-data-engineer | Data | Org purge deletes 4 of 6 ClickHouse tenant tables; `usage_facts` and `evidence_events` survive. | `services/worker/app/tasks/org_deletion_stores.py:17-31` |
| P1-21 | ibex-platform-engineer | Data | `failed_tasks` has no RLS/prune and stores args/tracebacks that can embed content; never purged on org delete. | `000021_create_failed_tasks.up.sql:2,15` |
| P1-22 | ibex-platform-engineer | Data | No v0.1.9→head upgrade path or rehearsal (39 → 58 migrations). | tag `v0.1.9` vs `6f12c96c` |
| P1-23 | ibex-qa | Data | Down migrations are unproven: 5 tests call `Down()`, no up→down→up cycle. | `infra/migrations/postgres/*_test.go` |
| P1-24 | ibex-data-engineer | Data | Object-store copies are not proven purged; no bucket lifecycle rule. | `site/content/docs/11.operations/10.data-lifecycle-and-deletion.md:107` |
| P1-25 | ibex-sre | AI | Ranking gate is not a required check; a ranking regression can merge. | `.github/branch-protection-main.json:4-12`; `memory-benchmark.yml:368-470` |
| P1-26 | ibex-memory-intelligence | AI | v2 mode numbers never reach the site; only the saturated v1 series is published. | `site/public/benchmarks/ranking-quality-benchmark-data.json`; `build_quality_suite_published.py:46-60` |
| P1-27 | ibex-memory-intelligence | AI | `full_graph == hybrid_rerank`; `graph_mode_distinguished:false` is reported but not gated; the fix is stranded on an unmerged branch. | `baseline-modes.json:18-20`; `git show 58ea4660` |
| P1-28 | ibex-memory-intelligence | AI | No human-judged, double-labelled gold set; kappa is production-dead code. | `generate_gold_set_v2.py:1-12`; `services/memory/app/eval/agreement.py` |
| P1-29 | ibex-memory-intelligence | AI | v1 gate tolerance (5 % relative on 20 queries) cannot catch a single wrong query. | `regression_gate_common.py:60-70` |
| P1-30 | ibex-memory-intelligence | AI | Embedding models are version-less IDs; search never filters by `embedding_model`; no re-embed runbook. | `services/embedder/app/profiles.py:24-35`; `pgvector_store.py:19-34` |
| P1-31 | ibex-memory-intelligence | AI | No model provenance inventory (model, revision, licence, fallback); extraction defaults are floating aliases. | `services/worker/app/config.py:181-214`; `DEPENDENCIES.md:303-324` |
| P1-32 | ibex-platform-engineer | AI | Proxy model overlays are unknown to the context catalog, so overlay models silently degrade to directive-only. | `services/context/app/capability_catalog.py:44-49` |
| P1-33 | ibex-memory-intelligence | AI | The reranker is unnamed/unpinned and no artifact provides it; the gated row runs `stub/lexical-overlap@1`. | `services/memory/app/config.py:230-285`; `infra/reference/` |
| P1-34 | ibex-memory-intelligence | AI | The "data, not instructions" framing is emitted only when a directive exists; memory-only assemblies lack it. | `services/context/app/formatter.py:188-197` |
| P1-35 | ibex-memory-intelligence + ibex-security | AI | No injection-risk classifier or quarantine; instruction-like content is stored active and injected. | `services/memory/app/pii/service.py:82`; AGENTS.md §5.5 |
| P1-36 | ibex-sre | AI | Assembly deadline has no reserved pack/format slice; 40 ms server vs 45 ms client is unreconciled. | `services/context/app/config.py:45-66`; `PERFORMANCE.md:35-46` |
| P1-37 | ibex-memory-intelligence | AI | No shadow evaluation or drift alert; the 5.C.3 emitter does not exist. | `services/memory/app/eval/__init__.py:3-5` |
| P1-38 | ibex-qa | AI | CI extraction "quality" is 1.0 by construction (oracle-aligned cassette); live model runs are weekly/manual. | `run_eval.py:1-20`; `extraction-eval.yml:138-165` |
| P1-39 | ibex-sre | AI | Context assembly 50/100 ms targets are unmeasured; no live 100K artifact; assemble overhead not in the Go gate. | `PERFORMANCE.md:35-44`; `benchmarks/context/README.md` |
| P1-40 | ibex-platform-engineer | Product | No tenant provisioning route; "manage tenants" is out of band. | `routers/organizations.py:27-86`; `route_inventory.json` |
| P1-41 | ibex-platform-engineer | Product | Console hand-duplicates Zod schemas from OpenAPI; an additive API field can 502 the BFF. | `shared/operator/contracts.ts:1-40` |
| P1-42 | ibex-platform-engineer | Product | Memory returns `{"detail"}` while proxy/API return `{"error"}`. | `services/memory/app/http_validation.py:28-38` |
| P1-43 | ibex-platform-engineer | Docs | Quickstart's first command (`cp .env.example .env`) references an untracked file. | `site/content/docs/01.getting-started/03.quickstart.md:41,51` |
| P1-44 | ibex-platform-engineer | Docs | Two public pages carry stale Console counts (6 of 10 vs 8 of 10) and wrong surface status. | `site/content/docs/11.operations/08.console.md:14`; `02.architecture/01.overview.md:89` |
| P1-45 | ibex-sre | Docs | Public env reference omits the operator deployment variables. | `site/content/docs/12.deployment/02.environment-variables.md:1-5` |
| P1-46 | owner | Docs | No 1.0 upgrade guide and no support window/matrix. | `site/content/docs/12.deployment/`; `13.reference/04.compatibility.md:11,72` |
| P1-47 | ibex-sre | Ops | No load/soak evidence; the only k6 run had 15.7 % failures and is explicitly not SLO evidence. | `00-status-and-evidence.md:70`; `benchmarks/k6/proxy_load.js` |
| P1-48 | ibex-platform-engineer | Ops | Context has no `/metrics`; api/relay/console are unscraped. | `infra/monitoring/prometheus/prometheus.yml:14-98` |
| P1-49 | ibex-sre | Ops | The OTel→Tempo path is never asserted; "best-effort" smoke only. | `infra/scripts/observability-smoke.sh:88-96` |
| P1-50 | ibex-sre | Ops | Relay has no image and is excluded from the manifest; mcp-operator has a Dockerfile but no publish job. | no `services/relay/Dockerfile`; `RELEASING.md:29-33` |
| P1-51 | owner | Claims | README says the platform "attaches evidence to every request"; the finalizer is post-response and the relay is default-off. | `README.md:14`; `00-status-and-evidence.md:55-57` |
| P1-52 | ibex-sre | Claims | The 20 ms proxy figure is a target; no published full-chat p99 exists. | `00-status-and-evidence.md:70` |

## 5. P2 — may ship as a documented limitation

| ID | Owner role | Domain | Finding |
|---|---|---|---|
| P2-01 | ibex-platform-engineer | Services | Worker registers no-op task skeletons (`extraction_noop`, `embedding_noop`, …) visible on a 1.0 install. |
| P2-02 | ibex-architect | Services | Four shared packages have zero importers; the worker carries a second object-store client. |
| P2-03 | ibex-data-engineer | Contracts | ClickHouse schema evolution has no gate; acceptable only while declared projection-only. |
| P2-04 | ibex-platform-engineer | Claims | `API_DOCUMENTATION.md` still says the chat route returns `501`. |
| P2-05 | owner | Claims | Two of ten core Console surfaces remain `preview`; Settings is illustrative and carries `[NEEDS-BACKEND]`. |
| P2-06 | ibex-sre | Security | `JWT_KEYSET_GRACE_SECONDS` is read by no code; rotation has no runbook. |
| P2-07 | ibex-qa | Security | Console BFF has no two-tenant browser evidence (bounded by the API). |
| P2-08 | ibex-memory-intelligence | Security | Memory create takes `agent_id` from the body; the composite FK is the only control and surfaces as a 500. |
| P2-09 | ibex-platform-engineer | Security | No whole-body size cap on API/memory/MCP; field bounds only. |
| P2-10 | ibex-qa | Data | Migration suite is not hermetic (interrupted run poisons the shared DB). |
| P2-11 | ibex-data-engineer | Data | `DATABASE_SCHEMA.md` documents 29 of 42 tables; no drift check. |
| P2-12 | ibex-data-engineer | Data | `usage_facts` has no TTL/retention class. |
| P2-13 | ibex-sre | Data | Seed on a deployed install: `db-seed.sh` refuses non-local hosts and `IBEX_ENV=production`, but it accepts the default localhost DSN, and the committed seed token is public. A single-node 1.0 install that runs it creates an active owner-role credential. |
| P2-14 | ibex-data-engineer | Data | Two irreversible migration families; the release note does not name them. |
| P2-15 | ibex-data-engineer | Data | `idempotency_ledger` / `budget_reservations` have no retention/reaper. |
| P2-16 | ibex-platform-engineer | AI | `tokens_used` omits tool-schema and formatter overhead; reserve ignores `max_tokens`. |
| P2-17 | ibex-platform-engineer | AI | Token counts are heuristics with 2–5 % buffers. |
| P2-18 | ibex-platform-engineer | Product | Capture policies and legal holds are unpaginated. |
| P2-19 | ibex-platform-engineer | Product | SSE drain returns an ad-hoc error envelope with no `request_id`. |
| P2-20 | ibex-platform-engineer | Product | `/ready` ignores Redis though operator SSE depends on it. |
| P2-21 | ibex-platform-engineer | Product | Platform ingestion lag is a live field hardcoded to null. |
| P2-22 | ibex-security | Product | No rate limiting on the management API, including login. |
| P2-23 | ibex-platform-engineer | Docs | Management API reference omits the live operator read routes. |
| P2-24 | ibex-sre | Ops | `check-helm-digest-placeholders.sh` is not wired into CI (it fails today). |
| P2-25 | ibex-security | Ops | Dependabot covers Docker for 2 of 8 build dirs; no scheduled base-image rebuild; waivers expire silently. |

## 6. Recommended 1.0 scope

**Decided 2026-11-06:** [ADR-0097](../adr/0097-v1-supported-profile.md) selects the profile below and records its
component, transport, dependency and readiness contracts. The recommendation is kept here for context; the ADR is the
controlled text.

Declare **one** profile and exclude the rest in writing:

> **v1.0 supported profile: single-node self-hosted Docker Compose.** Auth, proxy, api, memory, context, embedder, worker and console, each with a published, digest-pinned image, one TLS-terminated published origin, one-command startup, and a one-shot migration gate. PostgreSQL 16 + pgvector and Redis 7.4 are required; semantic memory requires a pinned TEI/bge-m3 backend; ClickHouse and MinIO are optional projections. Kubernetes, HA, hosted SLO measurement, response-bound evidence acknowledgement, the run envelope, DecisionService, MCP writes and the platform-tier Console surfaces are **out of 1.0 scope**.

That resolved D5 and gives every other gate a target. Without a named profile, "production-readiness" has no meaning and
no evidence can be scored. Two components the earlier draft of this section missed, both required by ADR-0097: the edge
TLS terminator (the Console BFF refuses to carry a session cookie to a non-HTTPS API origin) and a real embedding
backend. The bundle reaches the schema's `vector(1024)` constraint by forcing `IBEX_EMBEDDING_DIM=1024` on the stub, so
writes succeed — the gap is that the geometry carries no meaning, not that rows are rejected. A semantic-retrieval claim
therefore needs the pinned TEI/bge-m3 backend, which does not exist yet.

## 7. Sequenced plan

| Wave | Work | Exit gate |
|---|---|---|
| W1 — profile and truth | Name the profile (D5); run the G0 review before 2026-11-10; downgrade or renew the ledger; reword the README/API-doc claims | Signed profile + refreshed ledger |
| W2 — deliverability | Context image + transport decision; Console image; one compose profile on the critical path; Kubernetes explicitly excluded | One command starts the documented journey on a clean host |
| W3 — tenancy and erasure | `ibex_app` in every service; remove or role-gate the `is_service_account` bypass; org-delete FK fix; forget erases content; ClickHouse/object-store purge; two-tenant test per path | Cross-tenant negative suite green in the selected profile **and** a seeded org deletion reaching `succeeded` with zero rows **and** a forget that erases content |
| W4 — recovery | Scheduled backups + WAL; PITR drill; signed RPO/RTO table | One green drill per release, `rpo_pass=true` |
| W5 — contracts | `buf-breaking` required; OpenAPI breaking gate; registry for 75 routes/3 gRPC services/8 MCP tools; deprecation policy | A breaking change fails CI; registry diff is empty |
| W6 — observability | Real Alertmanager receiver; SLOs + burn alerts; context `/metrics`; trace round-trip | A synthetic alert reaches on-call; one trace asserted end to end |
| W7 — release integrity | `VERSION_RELEASE_TOKEN`; signed tag; signed+schema-validated manifest; per-image SBOM; verify signatures; reproducible builds; bundle smoke on the tag | `v0.2.0` cut entirely by the pipeline, then re-run for 1.0 |
| W8 — quality evidence | Reproducible ranking baseline; v2 on the site; graph subset fixed; model inventory; overlay fix; safety framing; quarantine | Published numbers reproduce from the commit |
| W9 — operator product | Login/logout, cookie+CSRF mutations, provisioning, all 10 core surfaces live or scope cut; docs parity | Clean-browser Playwright journey with no fixture cookie |

W1 is time-boxed by 2026-11-10. W2–W4 are the hard security/data core. W5–W7 make the release defensible. W8–W9 make it usable.

## 8. Method and limits

- Six read-only domain audits at `6f12c96c`: architecture/contracts, security/tenancy, data/recovery, AI/retrieval, product/API, operations/release. The 2026-11-06 amendment at `b400070f` added P0-22 and closed P0-17 at the decision level, both from the ADR-0097 review; every other row keeps its original base.
- Static review plus targeted local commands where possible (migration suite, release-manifest tests, Helm placeholder guard, compose validation, context/proxy test suites). No hosted origin, cluster, ClickHouse, PITR or p99 run was available to this audit, so every such item is recorded as **unverified**, not as passing.
- Findings are merged and deduplicated by the lead; IDs map to the domain audits (`R*`, `TM/AUT/BND/SEC/ISO/INP/SUP`, `D*`, `AI-*`, `AUTH/CONSOLE/API/CONTRACT/DOC/PKG`, `REL/DEP/CI/OBS/REC/CAP`).
- Nothing in this document changes a status, closes a gap, or authorises runtime work.
