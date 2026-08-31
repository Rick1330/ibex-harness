# Phase 3 Exit Audit — Detailed Gap Register

**Date:** 2026-08-31  
**Git SHA (`main` at audit):** `45696a2`  
**Branch:** `docs/m3-e5-phase3-exit-audit`  
**Gate milestone:** 3.E.5 Phase 3 exit audit  
**Tracks:** A (schema), B (vector store), C (write pipeline), D (read/ranking), E (exit gate)

---

## Executive summary

Phase 3 delivers the core memory substrate: schema v2 with HNSW, vector store abstraction, nine-step write pipeline (PII, dedup, temporal conflict, orchestration, multi-label), semantic search with composite ranking, hot cache read path, ISO-* security integration (12 cases), e2e lifecycle smoke, and retrieval-quality CI gates (HNSW + ranking + write pipeline).

**Verdict:** Phase 3 is substantively complete with **zero open P0 gaps**. Remaining items are P2 hygiene (schema doc drift, eval harness gaps) and P3 explicit deferrals (#641, #627, #642, #647, 1M full-profile benchmark, real MCP tools in Phase 3.5.E.2).

The original 3.E.5 exit-criteria list included a misplaced MCP E2E criterion and org-scope GDPR language; both are corrected in this register and the unified 10-item exit criteria published with the sign-off PR.

---

## Severity definitions

| Level | Meaning |
|-------|---------|
| **P0** | Blocker — must be green before Phase 3.5 |
| **P1** | High — fix at exit gate or immediately after |
| **P2** | Hygiene — fix before phase sign-off PR or document as accepted debt |
| **P3** | Defer — document as Phase 3.5+ / Phase 4; not hidden |

---

## P0 — Blockers

**None found.** All memory CI gates (`memory-test`, `memory-integration`, `memory-security-integration`, `e2e-smoke-p3-memory`) are wired into `ci-gate-python` / `ci-gate-go`. Published benchmark JSON on `main` (2026-08-31) reports `status: pass` for HNSW, ranking-quality, and write-pipeline suites.

---

## P1 — High

**None found.** No blocking correctness or security defects identified in live code review for Tracks A–E.

---

## P2 — Hygiene

### GAP-3-P2-001 — `DATABASE_SCHEMA.md` missing `memory_conflict_escalations`

| Field | Value |
|-------|-------|
| **Track** | A |
| **Evidence** | Migrations `000019` / `000020` create `ibex_core.memory_conflict_escalations` and `memory_conflict_escalation_status` ENUM; `grep memory_conflict` in `DATABASE_SCHEMA.md` returns no matches |
| **Remediation** | Add CREATE TABLE + ENUM block to `DATABASE_SCHEMA.md`; cite migrations 000019–000020 |
| **Status** | **Open** — documented; fix in Phase 3.5 hygiene or dedicated schema-doc PR |

### GAP-3-P2-002 — `memory_versions` documented but not migrated

| Field | Value |
|-------|-------|
| **Track** | A |
| **Evidence** | `DATABASE_SCHEMA.md` lines ~742–773 define partitioned `memory_versions`; no `memory_versions` migration under `infra/migrations/postgres/` |
| **Remediation** | Mark as aspirational in schema doc or defer migration to Phase 3.5+ extraction/versioning work |
| **Status** | **Open** — documented; not a Phase 3 deliverable |

### GAP-3-P2-003 — ADR-0057 status column vs migration 000020 ENUM

| Field | Value |
|-------|-------|
| **Track** | B |
| **Evidence** | ADR-0057 DDL shows TEXT + CHECK; live DB uses `ibex_core.memory_conflict_escalation_status` ENUM after `000020` |
| **Remediation** | Update ADR-0057 DDL snippet to match 000020 |
| **Status** | **Open** — doc drift only; runtime matches migration |

### GAP-3-P2-004 — PII structured recall fixture not CI-gated

| Field | Value |
|-------|-------|
| **Track** | C |
| **Evidence** | `benchmarks/memory/pii/recall_structured.json` — `n=20`, `recall=1.0`, `pass=true`; no `.github/workflows` reference to `recall_structured` |
| **Remediation** | Add optional CI job or document manual refresh cadence in ADR-0054 |
| **Status** | **Open** — measured recall meets >95% goal; gate is manual |

### GAP-3-P2-005 — No labeled conflict-detection precision benchmark

| Field | Value |
|-------|-------|
| **Track** | C |
| **Evidence** | `test_conflict_service.py` covers sequential supersede + overlapping escalation inline; no `benchmarks/**/conflict*` gold set |
| **Remediation** | Add labeled ambiguous-interval eval harness in Phase 3.5 or Track C hygiene |
| **Status** | **Open** — unit/e2e coverage sufficient for Phase 3 exit; precision not quantified |

### GAP-3-P2-006 — Stale exit criteria on 3.E.5 milestone page

| Field | Value |
|-------|-------|
| **Track** | E |
| **Evidence** | 3.E.5 listed MCP E2E + 11 criteria; Phase 3 scope excludes proxy hot path and real MCP tools |
| **Remediation** | Unify to 10-item corrected list in sign-off PR |
| **Status** | **Resolved** in 3.E.5 sign-off PR |

---

## P3 — Deferred (explicit)

| ID | Item | Rationale | Destination |
|----|------|-----------|-------------|
| GAP-3-P3-001 | Org-scope GDPR delete + MinIO archive purge + partial-failure orphan-detection | ISO-2.2 not implemented; no org-delete API in Phase 3 | Phase 4.A.2 ([#641](https://github.com/Rick1330/ibex-harness/issues/641)) — issue CLOSED as deferral tracker |
| GAP-3-P3-002 | Escalation worker consuming `memory_conflict_escalations` | `NoopConflictClassifier` + durable rows sufficient for Phase 3 | Phase 3.5+ ([#627](https://github.com/Rick1330/ibex-harness/issues/627)) |
| GAP-3-P3-003 | Tier-2 async Presidio re-scan on read path | Tier-1 regex guard ships; contextual PII residual risk documented | Phase 3.5+ ([#642](https://github.com/Rick1330/ibex-harness/issues/642)) |
| GAP-3-P3-004 | Explicit Redis `ZREM` / object-cache invalidation on SQL delete | Hydrate-on-read drops stale members per ADR-0059 | Phase 3.5+ ([#647](https://github.com/Rick1330/ibex-harness/issues/647)) |
| GAP-3-P3-005 | HNSW 1M-row full-profile benchmark on default CI | `has_1m: false` on smoke/fast profile by design (`publish_cells.py`, `test_build_published_data.py`) | Informational; run `full` profile manually or on schedule |
| GAP-3-P3-006 | CodeRabbit / Sonar / CodeScene advisory findings from Phase 3 PRs | Not machine-auditable from repo | Manual review backlog; advisory only |
| GAP-3-P3-007 | MCP `search_memory` / `write_memory` E2E with ClickHouse tracing | Stubs only (`services/mcp-memory/app/tools.py` — `persisted: False`) | Phase 3.5.E.2 ([milestone](/roadmap/phase-3-5-extraction-assembly/milestones/3.5.e.2-search-write-memory-tools)) |

---

## Phase 3 exit criteria — evidence matrix (corrected 10-item list)

| # | Criterion | Evidence | Status |
|---|-----------|----------|--------|
| 1 | Write pipeline passes unit + ISO-* tests | CI jobs `memory-test`, `memory-integration`, `memory-security-integration` in `ci-gate-python` / `ci-gate-go` | **Pass** |
| 2 | HNSW recall@10 ≥ 98% on committed CI profile; 1M optional on smoke/fast | `hnsw-benchmark-data.json` latest run `worst_recall_at_10: 1.0`, `gate_summary.recall_ok: true`, `has_1m: false` (expected) | **Pass** (smoke/fast profile) |
| 3 | Temporal conflict: sequential supersede, overlapping escalate, no LLM on non-overlap | `test_sequential_fact_supersedes_without_llm`, `test_overlapping_intervals_escalate_to_classifier`; `verify_phase3_memory_e2e.sh` | **Pass** |
| 4 | Retrieval-quality benchmarks in CI with baselines | `ranking-quality-benchmark-data.json`, `write-pipeline-benchmark-data.json` — `status: pass` 2026-08-31; `memory-benchmark.yml` regression gates | **Pass** |
| 5 | All 12 ISO-* cross-tenant cases pass | `memory-security-integration-test-ci.sh` requires ≥12 `test_memory_iso_*`; includes ISO-1.4 relationships cross-org | **Pass** |
| 6 | Per-memory FK cascade (ISO-2.1); org-scope GDPR deferred | `test_memory_iso_2_1_memory_delete_cascades_fk_children`; ADR-0060 §4; #641 deferred | **Pass** (per-memory only) |
| 7 | Phase 1 + 2 security regression tests pass | `security-integration` in `ci-gate-go` | **Pass** |
| 8 | `make e2e-smoke-p3-memory` exits 0 | CI job `e2e-smoke-p3-memory` in `ci-gate-python` | **Pass** |
| 9 | Phase 3 ADRs 0047–0049, 0052–0061 published | ADR nav through 0061; [decisions.mdx](/roadmap/phase-3-memory-engine/decisions) | **Pass** |
| 10 | No proxy hot-path changes in Phase 3 | `git log e66e359..45696a2 -- services/proxy/internal/handler services/proxy/internal/middleware services/proxy/cmd/proxy` — empty; only `services/proxy/Dockerfile` touched in #600 | **Pass** |

**Relocated:** MCP `search_memory`/`write_memory` E2E → GAP-3-P3-007 (Phase 3.5.E.2). Phase 2.5 delivered MCP skeleton only (ADR-0050).

---

## Track A — Schema & migrations (000014–000020)

| Migration | Ships | `DATABASE_SCHEMA.md` |
|-----------|-------|----------------------|
| 000014 | `memories` foundation + RLS + temporal columns | Aligned |
| 000015 | `memory_labels` + primary sync trigger | Aligned |
| 000016 | `memory_relationships` + supersession view | Aligned |
| 000017 | HNSW index (`m=16`, `ef_construction=64`), quality cols, `search_vector` | Aligned |
| 000018 | Partial unique on active `content_hash` | Aligned |
| 000019 | `memory_conflict_escalations` table | **Missing** (GAP-3-P2-001) |
| 000020 | `memory_conflict_escalation_status` ENUM | **Missing** (GAP-3-P2-001) |

**HNSW build parameters:** documented in 000017, ADR-0052, ADR-0053, ADR-0061, `benchmarks/memory/publish_cells.py` (`ef_search=40` query-time GUC).

---

## Track B — ADR fidelity (0047–0049, 0052–0061)

| ADR | Status | Notes |
|-----|--------|-------|
| 0047 | Implemented | Temporal validity columns, RLS |
| 0048 | Implemented | `memory_labels` multi-label |
| 0049 | Implemented | `memory_relationships` graph |
| 0052 | Implemented | Schema v2 expand, HNSW |
| 0053 | Implemented | `PgVectorStore`, composite scoring |
| 0054 | Implemented | In-process Presidio PII |
| 0055 | Implemented | Write-path dedup |
| 0056 | Implemented | Temporal-interval conflict |
| 0057 | Implemented | Write orchestration; doc drift GAP-3-P2-003 |
| 0058 | Implemented | Semantic search FTS fallback |
| 0059 | Implemented | Hot cache read path |
| 0060 | Implemented | Tenant isolation + ISO-* CI |
| 0061 | Implemented | Benchmark methodology + gates |

---

## Track C — Write pipeline

| Check | Result |
|-------|--------|
| `POST /v1/memories` nine-step pipeline | Shipped 3.C.1–3.C.5 |
| PII structured recall | 20/20 (`recall_structured.json`); not CI-gated (GAP-3-P2-004) |
| Sequential-fact zero LLM | Unit test + e2e |
| Overlapping-interval escalation | Unit test + e2e escalation row |
| `memory_conflict_escalations` durable rows | Migration 000019; worker deferred #627 |

---

## Track D — Read/ranking + hot cache

| Check | Result |
|-------|--------|
| `POST /v1/memories/search` semantic path | 3.D.1 shipped |
| Composite scoring in ranking | 3.D.2 + ranking-quality gold set v1 |
| `MemoryHotCacheReader` + top-50 trim | 3.D.3 ADR-0059 |
| Cross-org search isolation | ISO-1.1, ISO-1.5 |

---

## Track E — Exit gate

### ISO-* matrix (12 cases)

| ID | Test | Status |
|----|------|--------|
| ISO-1.1 | Cross-org search empty | Covered |
| ISO-1.2 | Cross-org agent forbidden | Covered |
| ISO-1.3 | RLS floor malformed WHERE | Covered |
| ISO-1.4 | Relationship cross-org insert rejected | Covered |
| ISO-1.5 | HNSW no cross-org leakage | Covered |
| ISO-1.6 / 1.8 | Hot cache agent isolation (parametrized) | Covered |
| ISO-1.7 | Conflict escalations RLS isolation | Covered |
| ISO-2.1 | Per-memory DELETE cascades FK children | Covered |
| ISO-2.2 | Org-scope GDPR + MinIO | **Deferred** #641 (GAP-3-P3-001) |
| ISO-3.1 | Tier-1 PII bypass blocked on search | Covered (2 cases) |
| ISO-3.2 | Quarantined never in search | Covered |

### Benchmark freshness (latest on `main`, 2026-08-31)

| Suite | File | `status` | Notes |
|-------|------|----------|-------|
| HNSW | `web/public/benchmarks/hnsw-benchmark-data.json` | pass | recall@10=1.0, 10K+100K cells |
| Ranking | `web/public/benchmarks/ranking-quality-benchmark-data.json` | pass | gold set v1, 20 queries |
| Write | `web/public/benchmarks/write-pipeline-benchmark-data.json` | pass | p95=47.3ms < 200ms SLA |

---

## Track E — CI inventory (memory-related)

**Required on `ci-gate-python` / `ci-gate-go`:**

| Job | Script | Gate |
|-----|--------|------|
| `memory-test` | `memory-test-ci.sh` | both |
| `memory-coverage` | `memory-test-ci.sh` + coverage gate | both |
| `memory-integration` | `memory-integration-test-ci.sh` | both |
| `memory-security-integration` | `memory-security-integration-test-ci.sh` | both |
| `e2e-smoke-p3-memory` | `memory-e2e-test-ci.sh` | **python only** |
| `mcp-memory-test` | `mcp-memory-test-ci.sh` | both |
| `mcp-memory-coverage` | mcp-memory tests + coverage | both |

**Benchmark workflow (`memory-benchmark.yml`):** `collect-hnsw-benchmarks`, `collect-ranking-quality`, `collect-write-pipeline-bench` — regression gates via `check_hnsw_gate_status.py` and suite-specific gate scripts.

**Phase 1/2 regression:** `security-integration` required on `ci-gate-go`.

---

## What was already solid at audit

- HNSW index from day one (no IVFFlat migration debt)
- Composed tenant isolation (RLS + app-layer `org_id` + Redis namespacing) proven in CI
- Write pipeline ordering (PII before embed) enforced in orchestrator
- Category-conditional composite scoring wired through search and hot cache
- Benchmark bot publish pipeline with committed baselines and CI regression gates

---

## Sign-off criteria (post-audit)

- [x] Gap register complete (this document — `032-phase3-exit-audit.md`)
- [x] Public summary published (`phase3-exit-audit.mdx`)
- [x] Zero open P0 gaps
- [x] All 12 ISO-* cases pass (`pytest -m security_integration`)
- [x] `memory-security-integration` required on `main`
- [x] Corrected 10-item exit criteria verified against evidence
- [x] `current-state` reflects Phase 3 complete
- [ ] P2 hygiene items (GAP-3-P2-001–005) — open, documented, non-blocking
