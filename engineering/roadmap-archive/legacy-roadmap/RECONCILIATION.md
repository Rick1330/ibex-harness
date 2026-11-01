# Legacy roadmap reconciliation (2026-11-01)

**Status:** Historical crosswalk. This record explains how the legacy Phase 4, 4.5, and 5 pages relate to the current
product boundary. It does not promote any milestone, and it does not rewrite dated records.

Current truth remains:

- `engineering/architecture-v2/00-status-and-evidence.md` — capability ledger.
- `engineering/architecture-v2/18-gap-register.md` — open GAPs and their dispositions.
- `services/console/shared/operator/surfaces.ts` — Console surface tiers and availability.
- [ADR-0089](../../adr/0089-product-shape-and-console-scope.md) — memory/context product shape and Console scope.
- [ADR-0090](../../adr/0090-retire-dashboard-compatibility-shell.md) — dashboard compatibility shell retired.

## Status vocabulary

| Label | Meaning |
| --- | --- |
| `done*` | Implemented and mounted locally; the ledger records the capability as `shipped-local`. Hosted, HA, and SLO evidence are separate. |
| `partial` | Some code or evidence exists; the milestone's acceptance condition is not met. |
| `not done` | No implementation or acceptance evidence found. |
| `superseded` | The premise or deliverable was replaced by a later decision. |

## Phase 4 — Operator Platform & Multi-Provider

| Milestone | Legacy claim | Status | Evidence and boundary |
| --- | --- | --- | --- |
| 4.A.1–A.5 | Management CRUD complete | `done*` | API routers are mounted (`services/api/app/main.py`); the ledger records the Management API as `shipped-local`. The `4.A.2` frontmatter still says `planned`; that label is stale, not a status contradiction. |
| 4.B.1–B.3 | Hierarchical rate limits, config API, load gate | `done*` | `packages/ratelimit`, API config routes, and the load-gate CI job exist; the ledger records rate limiting as `shipped-local`. No hosted Redis HA or measured latency SLO is claimed. |
| 4.C.1–C.3 | Anthropic, routing, breakers | `done*` | Provider bootstrap and proxy routing exist; the ledger records them as `shipped-local`. No hosted provider-conformance matrix or provider-failure soak is claimed. |
| 4.C.4–C.5 | Fallback and streaming hardening | `partial` | Fallback and stream forwarding exist. Streaming hardening remains provisional in the ledger; no slow-client/leak soak evidence. |
| 4.P.0–P.1 | Runtime topology and identity | `partial` | The operator session API exists behind a default-off feature flag. There is no login product, hosted ingress, or two-tenant evidence. The dashboard preview workflow is retired by ADR-0090. |
| 4.P.2–P.4 | Evidence, privacy, cost platform | `partial` | Evidence and budget migrations and routers exist. Response-bound acknowledgement, ClickHouse production delivery, and cost reconciliation remain open (GAP-005, GAP-006, GAP-011). |
| 4.P.5–P.6 | Recovery and assurance harness | `partial` | Helm is scaffolding with sentinel digests; the P6 manifest exists. No production origin, RPO proof, or E1–E4 evidence. |
| 4.D.0–D.2 | Console shell, overview, trace inspector | `partial` | Console shell and live Overview/Platform/Explore exist; Agents is now live too. No hosted two-tenant evidence. |
| 4.D.3–D.6 | Sessions/replay, incidents, directives, cost | `superseded` | ADR-0089 moved these to preview or platform-tier; none has an owning operator contract. |
| 4.E.1–E.4 | Release gates | `not done` | No production deployment, recovery drill, replay, or zero-P0 release evidence. |

## Phase 4.5 — Intelligence Layer

| Milestone | Legacy claim | Status | Evidence and boundary |
| --- | --- | --- | --- |
| 4.5.A.1–C.3 | Fingerprints, drift, regression runner | `not done` | No behavioral-fingerprint migration or runtime. Drift exists only as Console preview fixtures. |
| 4.5.C.4, D.1–D.4 | Dashboard integration and exit gate | `superseded` | The dashboard shell is retired (ADR-0090), and ADR-0089 keeps drift in the platform tier until a named design partner and owning contract exist. |
| Exit premise | Proxy p99 <20 ms | `partial` | GAP-004 ratifies 20 ms as a **warm-path target**, not measured evidence. The local Go gate compares warm-path means, not p99; no recent passing full-chat p99 run is published. This is not hosted or production p99 evidence. |

## Phase 5 — Advanced Retrieval & Graph Memory

Phase 5 is **unstarted**. Several premises are stale, so the milestones are planning sketches, not a committed queue.

| Milestone | Legacy claim | Status | Evidence and boundary |
| --- | --- | --- | --- |
| 5.A.1 | Parallel BM25 channel | `partial` | Full-text search exists as a short-vector fallback (`services/memory/app/read/full_text.py`), not as a parallel first-class channel. |
| 5.A.2–A.3 | RRF and cross-encoder rerank | `not done` | No RRF function or rerank client found. |
| 5.B.1–B.3 | Graph traversal, scoring, lineage tool | `partial` | A bounded supersession-tip resolver exists in migration `000016`; no retrieval path or MCP tool calls it. |
| 5.C.1–C.3 | Gold set v2, multi-mode benchmark, shadow | `not done` | `benchmarks/memory/ranking_quality/gold_set_v1.json` is 51 memories / 20 queries, dense-only. Target was ~500 / 150 with multi-mode and shadow evidence. |
| 5.D.1–D.2 | Retrieval sign-off and exit audit | `not done` | No sign-off record. |
| Stale premises | 40 ms context deadline, dashboard integration | `superseded` | GAP-004 classifies 40 ms as an internal client deadline; the dashboard shell is retired. |

## Contradictions resolved by this crosswalk

1. **Dashboard as a product.** Phase 4 and 4.5 pages treat the dashboard as the operator goal. ADR-0089 narrows the
   Console, and ADR-0090 retires the shell. The canonical application is `services/console`.
2. **`web/` and Next.js.** Several Phase 4 pages describe `web/` as the public site and Next.js as the Console. The
   public site is `site/` (Nuxt 4 + Docus); the Console is Nuxt 4 + Nitro.
3. **"Implemented-with-evidence".** Phase 4 findings use this label for slices the ledger keeps provisional. The
   ledger and gap register win; this is GAP-001.
4. **Snapshot dates.** `current-state.mdx` pins an older commit and ADR. Use the ledger for current status.
5. **Maturity claims.** "World-class operator dashboard" and "production-ready operator platform" are not supported by
   hosted, two-tenant, SLO, or recovery evidence.

## Still-valid work under the current shape

Ranked by fit with ADR-0089 and dependency order:

1. **`memory-context` supported bundle.** ADR-0089 §5 requires a tested bundle profile; the release manifest already
   has an empty `bundles` list. Smallest slice: compose profile (Auth, memory, embedder, pgvector, migrations), a smoke
   script, and a bundle status in `release-manifest.json`.
2. **Memories operator read model.** The core Memories surface is preview with no operator router. Smallest slice: a
   tenant-scoped list/detail projection with validity and conflict metadata, a BFF, and a read-model flip.
3. **Sessions read model and turn-to-trace join.** The trace API exists; there is no session-to-trace join. Smallest
   slice: read-only session list/detail keyed to trace IDs, without replay.
4. **Evidence certification summary.** The surface is preview; outbox and relay exist. Smallest slice: org-scoped counts
   of certified, uncertified, and tombstoned records, with no raw payloads.
5. **GAP-007 typed memory lifecycle.** Define and test lifecycle and revision-ledger semantics before any write path is
   promoted. This is a prerequisite for accepted memory provenance, not a UI slice.

## Archive handling

- Phase 4 and 4.5 pages carry a historical banner. Phase 5 pages carry an unstarted/stale-premise banner.
- Dated `findings.mdx` entries, Phase 0–3.5 pages, exit audits, and `ROADMAP_CONVENTIONS.mdx` stay unchanged.
- Delete nothing. New findings are appended; history is not rewritten.
