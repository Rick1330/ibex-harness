import type {
  OperatorContext,
  OperatorOverview,
  OperatorTrace,
  OperatorTraceDetail,
  OperatorTraceList,
  PlatformHealth,
} from "~~/shared/operator/contracts"

/**
 * Development-only illustrative reads.
 *
 * The console must not silently replace a failed live read in production. In
 * development, these fixtures let the shell, charts, and empty-state design be
 * reviewed without an operator API running. Every surface that uses them still
 * renders the `Illustrative` provenance chip and makes no live claim.
 */
export const CONSOLE_DEMO_ENABLED = import.meta.dev

/**
 * Resolve demo mode for a request.
 *
 * Demo fixtures are compile-time development-only. `?demo=1` cannot enable
 * them in a production build; `?demo=0` forces the fail-closed live path in
 * development.
 */
export function resolveDemoMode(enabled: boolean, demoParam: unknown): boolean {
  if (!enabled) return false
  return demoParam !== "0"
}

const ORG_ID = "00000000-0000-4000-8000-000000000000"
const SESSION_ID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
const RUN_IDS = [
  "b1c2d3e4-f5a6-4b7c-8d9e-0f1a2b3c4d5e",
  "c2d3e4f5-a6b7-4c8d-9e0f-1a2b3c4d5e6f",
  "d3e4f5a6-b7c8-4d9e-8f01-2a3b4c5d6e7f",
  "e4f5a6b7-c8d9-4e0f-9a12-3b4c5d6e7f80",
  "f5a6b7c8-d9e0-4f1a-8b23-4c5d6e7f8091",
  "a6b7c8d9-e0f1-4a2b-9c34-5d6e7f8091a2",
  "b7c8d9e0-f1a2-4b3c-8d45-6e7f8091a2b3",
  "c8d9e0f1-a2b3-4c4d-9e56-7f8091a2b3c4",
]

const OBSERVED_AT = "2026-10-30T15:12:00Z"
const QUERY_START = "2026-10-30T09:12:00Z"
const QUERY_END = "2026-10-30T15:12:00Z"

function trace(index: number, status: "ok" | "error", completeness: "complete" | "partial" | "sampled"): OperatorTrace {
  return {
    trace_id: `trace-${String(index + 1).padStart(2, "0")}`,
    run_id: RUN_IDS[index]!,
    request_id: `req-demo-${String(index + 1).padStart(3, "0")}`,
    agent_id: null,
    session_id: SESSION_ID,
    checkpoint_id: null,
    status,
    error_code: status === "error" ? (index % 2 === 0 ? "provider_timeout" : "span_gap") : null,
    started_at: `2026-10-30T${String(14 - Math.floor(index / 2)).padStart(2, "0")}:${String(58 - index * 6).padStart(2, "0")}:00Z`,
    ended_at: `2026-10-30T${String(14 - Math.floor(index / 2)).padStart(2, "0")}:${String(58 - index * 6).padStart(2, "0")}:04Z`,
    duration_ms: 1_180 + index * 940,
    evidence: {
      schema_version: "operator.trace-read.v1",
      capture_mode: "metadata",
      completeness,
      sample_decision: "kept",
      freshness: "fresh",
      retention: "unknown",
      source: "postgres.evidence_runs",
      source_watermark: `outbox:${184_220 - index}`,
      publication_state: completeness === "complete" ? "published" : "partial",
      ingestion_lag_ms: 420 + index * 130,
      policy_version: "operator.trace-read.v1",
      observed_at: OBSERVED_AT,
    },
  }
}

export const DEMO_CONTEXT: OperatorContext = {
  schema_version: "operator.context.v1",
  org_id: ORG_ID,
  role: "owner",
  org_name: "Ibex Demo",
  org_slug: "ibex-demo",
  org_status: "active",
  observed_at: OBSERVED_AT,
}

export const DEMO_OVERVIEW: OperatorOverview = {
  schema_version: "operator.overview.v1",
  org_id: ORG_ID,
  org_name: "Ibex Demo",
  org_slug: "ibex-demo",
  org_status: "active",
  counts: {
    active_users: 12,
    agents: 24,
    active_agents: 18,
  },
  observed_at: OBSERVED_AT,
  completeness: "complete",
}

export const DEMO_TRACES: OperatorTrace[] = [
  trace(0, "ok", "complete"),
  trace(1, "ok", "complete"),
  trace(2, "error", "partial"),
  trace(3, "ok", "complete"),
  trace(4, "ok", "sampled"),
  trace(5, "error", "partial"),
  trace(6, "ok", "complete"),
  trace(7, "ok", "complete"),
]

export const DEMO_TRACE_LIST: OperatorTraceList = {
  schema_version: "operator.trace-list.v1",
  query_grammar_version: "operator.trace-query.v1",
  items: DEMO_TRACES,
  next_cursor: null,
  truncated: false,
  matched_count: DEMO_TRACES.length,
  returned_count: DEMO_TRACES.length,
  observed_at: OBSERVED_AT,
  query_start: QUERY_START,
  query_end: QUERY_END,
  limit: 50,
}

export const DEMO_TRACE_DETAIL: OperatorTraceDetail = {
  ...DEMO_TRACES[0]!,
  schema_version: "operator.trace-detail.v1",
  unavailable_sections: ["candidates", "directives", "tools", "content", "events"],
  spans: [
    {
      span_id: "span-1",
      parent_span_id: null,
      operation_kind: "support-triage",
      status: "ok",
      error_code: null,
      started_at: "2026-10-30T14:58:00Z",
      ended_at: "2026-10-30T14:58:00.320Z",
    },
    {
      span_id: "span-2",
      parent_span_id: "span-1",
      operation_kind: "retrieve_context",
      status: "ok",
      error_code: null,
      started_at: "2026-10-30T14:58:00.010Z",
      ended_at: "2026-10-30T14:58:00.080Z",
    },
    {
      span_id: "span-3",
      parent_span_id: "span-1",
      operation_kind: "generate_response",
      status: "ok",
      error_code: null,
      started_at: "2026-10-30T14:58:00.080Z",
      ended_at: "2026-10-30T14:58:00.330Z",
    },
  ],
  assembly: {
    budget_calculation_ms: 2,
    directive_load_ms: 4,
    hot_memory_retrieval_ms: 21,
    cold_memory_retrieval_ms: 8,
    ranking_ms: 6,
    packing_ms: 5,
    formatting_ms: 3,
    total_ms: 49,
    candidates_evaluated: 18,
  },
  candidates: [],
  directive: null,
  tools: [],
  score_schema_note: null,
}

export const DEMO_PLATFORM_HEALTH: PlatformHealth = {
  dependency_health: {
    postgres: "ok",
    redis: "ok",
    clickhouse: "degraded",
    minio: "ok",
    "llm-proxy": "ok",
    "auth-service": "ok",
    "memory-service": "ok",
    "context-engine": "ok",
    "worker-queue": "ok",
  },
  last_backup_at: "2026-10-30T13:00:00Z",
  last_restore_drill: { completed_at: "2026-10-28T04:00:00Z", status: "passed" },
  retention_horizon_days: 90,
  ingestion_lag_seconds: 42,
  dlq_depth: 0,
  degraded_mode: false,
  outbox_max_aggregate_seq: 184_220,
  deploy_image_digest: "sha256:2c81c81e9f2a4c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d",
  observed_at: OBSERVED_AT,
}


export function demoTraceDetail(runId: string): OperatorTraceDetail | null {
  const trace = DEMO_TRACES.find((entry) => entry.run_id === runId)
  if (!trace) return null
  return { ...DEMO_TRACE_DETAIL, ...trace, schema_version: "operator.trace-detail.v1" }
}

export function demoTraceRuns(traceId: string): OperatorTraceList | null {
  const items = DEMO_TRACES.filter((entry) => entry.trace_id === traceId)
  if (!items.length) return null
  return { ...DEMO_TRACE_LIST, items, matched_count: items.length, returned_count: items.length }
}
