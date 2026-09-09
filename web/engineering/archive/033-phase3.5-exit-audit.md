# Phase 3.5 Exit Audit — Detailed Gap Register

**Date:** 2026-09-09  
**Git SHA (`main` at audit):** `ae0272d6`  
**Branch:** `docs/3.5.f.3-benchmark-sign-off-adr-index`  
**Gate milestone:** 3.5.F.3 Benchmark sign-off and ADR index  
**Tracks:** A (worker), B (extraction), C (context assembly), D (proxy integration), E (MCP), F (exit gate)

---

## Executive summary

Phase 3.5 closes the learning loop: Celery extraction turns completed sessions into memories; the context assembly service packs memories into the proxy hot path under a degradation ladder; MCP `search_memory` / `write_memory` / `record_feedback` share the memory HTTP substrate; F.1 e2e smoke and F.2 ISO-MCP isolation are CI-gated.

**Verdict:** Phase 3.5 is substantively complete with **zero open P0 gaps**. Criterion #4 (latency budgets) is **partial** — proxy+assemble Go microbench and local `assemble_load` exist, but dedicated published suites / CI gates for context assembly at “20 concurrent”, MCP tool p95, and extraction throughput are **not** wired (documented as P2). Criterion #10 planning text named ADR-0043/0044; corrected interpretation cites ADR-0038, ADR-0050, and Phase 3.5 ADRs 0062–0072 (indexed in this sign-off).

---

## Severity definitions

| Level | Meaning |
|-------|---------|
| **P0** | Blocker — must be green before Phase 4 |
| **P1** | High — fix at exit gate or immediately after |
| **P2** | Hygiene — fix before next phase or document as accepted debt |
| **P3** | Defer — document as Phase 4+; not hidden |

---

## P0 — Blockers

**None found.** `e2e-smoke-p3.5` and `security-integration-p35` are required on Python/Go CI gates as applicable; F.1/F.2 landings on `main` (`8a320474`, `ae0272d6`) with green required checks. ADR-0038 and ADR-0050 remain Accepted; ADRs 0062–0072 Accepted and sidebar-indexed (`meta.json`).

---

## P1 — High

**None found.** No blocking correctness or security defects identified for Tracks A–F at sign-off. Fail-closed MCP auth and org RPM rate limit are covered by unit/integration tests from E.4; ISO-MCP-01..04 covered by F.2.

---

## P2 — Hygiene

### GAP-35-P2-001 — `contextAssembly` suite not published / not CI-gated

| Field | Value |
|-------|-------|
| **Track** | C / F |
| **Evidence** | `benchmarks/context/assemble_load.py` (local; stub p99&lt;50ms); Go `BenchmarkProxyChatOverheadWithAssemble` under **proxy** suite only; no `context-assembly-benchmark-data.json`, no site registry entry, no bot dispatch |
| **Remediation** | Wire collect job + publish path per suite contract column `contextAssembly`; gate p95 at documented concurrency |
| **Status** | **Open** — contract column documented in 3.5.F.3; CI deferred |

### GAP-35-P2-002 — `mcpTool` p95 suite missing

| Field | Value |
|-------|-------|
| **Track** | E / F |
| **Evidence** | No `*bench*` under `services/mcp-memory/`; Grafana MCP HTTP p95 + ClickHouse `mcp_tool_calls.latency_ms` only |
| **Remediation** | Add harness + publish `mcp-tool-benchmark-data` per suite contract; do not treat dashboards as the suite |
| **Status** | **Open** — documented |

### GAP-35-P2-003 — `extractionThroughput` suite missing

| Field | Value |
|-------|-------|
| **Track** | B / F |
| **Evidence** | `extractionQuality` suite (ADR-0066) measures quality, not worker throughput; no throughput collect job |
| **Remediation** | New suite_id `extractionThroughput` (already reserved in README); Celery events/inspector may inform ops but are not a publish contract |
| **Status** | **Open** — documented |

### GAP-35-P2-004 — Criterion #4 concurrency wording vs harness

| Field | Value |
|-------|-------|
| **Track** | C / F |
| **Evidence** | Exit criterion says “p95 &lt; 50ms at 20 concurrent”; `assemble_load` is open-loop RPS (default stub 500 RPS) with p99 assert — not a fixed concurrency=20 CI profile |
| **Remediation** | Either add a concurrency=20 CI profile or amend criterion wording in a follow-up docs PR after measurement |
| **Status** | **Open** — accepted measurement debt; not silently closed |

### GAP-35-P2-005 — ADR index prose lagged `meta.json` (0066–0072)

| Field | Value |
|-------|-------|
| **Track** | F |
| **Evidence** | Pre-sign-off `web/content/docs/adr/index.mdx` claimed “through ADR-0065” while sidebar listed through 0072 |
| **Remediation** | Extend index prose through ADR-0072 (this PR) |
| **Status** | **Resolved** in 3.5.F.3 sign-off PR |

### GAP-35-P2-006 — Milestone frontmatter status hygiene

| Field | Value |
|-------|-------|
| **Track** | F |
| **Evidence** | Several milestones used `implemented` / `complete` / `in-progress` / `planned` while work had shipped; hub UI maps only `completed` reliably |
| **Remediation** | Normalize all Phase 3.5 milestone `status` to `completed` in this PR |
| **Status** | **Resolved** in 3.5.F.3 sign-off PR |

---

## P3 — Deferred (explicit)

| ID | Item | Rationale | Destination |
|----|------|-----------|-------------|
| GAP-35-P3-001 | Carry-forward Phase 3 P2 schema doc gaps (conflict escalations, `memory_versions`, ADR-0057 ENUM drift) | Not Phase 3.5 scope; still open from 032 register | Schema-doc hygiene PR / Phase 4 |
| GAP-35-P3-002 | Escalation worker for `memory_conflict_escalations` | Still deferred from Phase 3 ([#627](https://github.com/Rick1330/ibex-harness/issues/627) CLOSED as deferral tracker) | Phase 4+ |
| GAP-35-P3-003 | Org-scope GDPR + MinIO cascade | Still deferred ([#641](https://github.com/Rick1330/ibex-harness/issues/641) CLOSED as deferral tracker) | Phase 4.A.2 |
| GAP-35-P3-004 | Per-tool / per-agent MCP rate limits | E.4 ships org-wide RPM only (`mcp-memory` README) | Phase 4 ops polish |
| GAP-35-P3-005 | Live 100K `assemble_load` as required CI | Live profile is manual / non-failing by design (`benchmarks/context/README.md`) | Scheduled / full-profile follow-up |
| GAP-35-P3-006 | Site registry + bot modules for new suite_ids | Contract-only in F.3; avoid inventing CI without harnesses | Follow-up bench PRs |

---

## Phase 3.5 exit criteria — evidence matrix

| # | Criterion | Evidence | Status |
|---|-----------|----------|--------|
| 1 | Extraction worker converts a completed session into correctly-categorized memories | `make e2e-smoke-p3.5` / `infra/scripts/e2e_phase35.sh` learning-loop; worker extraction + ADR-0063/0064/0065; CI `e2e-smoke-p3.5` | **Pass** |
| 2 | Subsequent chat request transparently injects a relevant memory | F.1 scenarios: terminate → extract → chat inject; proxy Assemble wiring (D.2) | **Pass** |
| 3 | Zero cross-tenant leakage across ISO-\* and ISO-MCP-\* | Phase 3 ISO-\* still gated; F.2 `security-integration-p35` (≥4 `iso_mcp` cases ISO-MCP-01..04) | **Pass** |
| 4 | Context assembly p95 &lt; 50ms @ 20 concurrent; proxy overhead &lt;20ms p99 non-provider | Local `assemble_load` stub p99&lt;50ms; published `BenchmarkProxyChatOverheadWithAssemble` ~0.4ms/op on `fast` (well under 20ms); **no** dedicated CI suite / concurrency=20 gate | **Partial** (GAP-35-P2-001/004) |
| 5 | All 4 degradation-ladder levels independently verified | Unit `services/context/tests/test_assemble.py` L0–L2; F.1 scenario5 L3 via `X-IBEX-Context-Fallback` (`e2e_phase35_scenarios.py`) | **Pass** |
| 6 | MCP search/write/feedback E2E, one substrate with proxy | E.2–E.3 tools → memory HTTP; feedback migration `000023`; mcp-memory tests + F.1 where applicable | **Pass** |
| 7 | MCP fail-closed on auth outage; independent rate-limit budget | `test_auth_unavailable_fail_closed`; auth breaker; Redis org RPM (`test_rate_limit_*`); E.4 | **Pass** |
| 8 | Phase 1–3 regression tests still pass | Required `ci-gate-*` jobs on F.1/F.2 merges (security-integration, memory-*, e2e-smoke-p3-memory, etc.) | **Pass** |
| 9 | `make e2e-smoke-p3.5` exits 0 | Makefile target + CI job `e2e-smoke-p3.5` | **Pass** |
| 10 | ADR-0038 / ADR-0043 / ADR-0044 published and indexed | **Corrected:** ADR-0038 + ADR-0050 + ADRs 0062–0072 Accepted and indexed; ADR-0043/0044 are tokenizer/response-pipeline (not Phase 3.5). Index prose updated through 0072 | **Pass** (corrected interpretation) |

---

## Track notes (sign-off)

| Track | Outcome |
|-------|---------|
| A | Celery skeleton + observability / DLQ (ADR-0062) |
| B | Prompt/schema v2, cost-tiered batch, idempotency, quality harness (ADR-0063–0066) |
| C | Budget → retrieve → score → pack → format → gRPC degradation (ADR-0067–0071) |
| D | Go client, handler fallback, headers, enqueue (ADR-0072), flags, integration tests |
| E | MCP transport + real tools + feedback + fail-closed auth + org RPM |
| F | Learning-loop e2e, ISO-MCP matrix, this benchmark/ADR sign-off |

---

## What was already solid

- ADR-0038 Accepted since 2026-07-19 (sketch “Pending → Accepted” was stale)
- ADR-0050 Accepted MCP skeleton reused for Track E (no ADR-0043/0044 reuse)
- Extraction **quality** suite already published (`extractionQuality`) from 3.5.B.4
- Proxy suite already collects `BenchmarkProxyChatOverheadWithAssemble`

## Sign-off criteria

- [x] Gap register complete (this document — `033-phase3.5-exit-audit.md`)
- [x] Public summary published (`phase35-exit-audit.mdx`)
- [x] Suite contract columns reserved for Phase 3.5 profiles
- [x] ADR index prose through ADR-0072
- [x] Phase 3.5 `decisions.mdx` committed
- [x] Zero open P0 / P1
