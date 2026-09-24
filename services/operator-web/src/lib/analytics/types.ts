/**
 * Analytics API contracts — mirrors GET /v1/analytics/overview,
 * /latency, /memory-performance. Permission: trace:read.
 *
 * Completeness comes from ClickHouse countIf(completeness != 'complete').
 * estimated_cost_usd is advisory — not the billing ledger.
 */

export type AnalyticsPeriod = "24h" | "7d" | "30d" | "90d"

export type BucketCompleteness = "complete" | "partial"

export type TopAgentRow = {
  agent_id: string
  name: string
  slug: string
  request_count: number
  token_count: number
}

/** Percentage map as returned by the API — UI caps at top N + Other. */
export type ModelDistribution = Record<string, number>

export type TimeBucket = {
  /** toStartOfHour(occurred_at) ISO hour. */
  hour: string
  requests: number
  tokens: number
  completeness: BucketCompleteness
}

export type AnalyticsOverview = {
  period: AnalyticsPeriod
  total_requests: number
  total_tokens: number
  total_sessions: number
  total_memories_created: number
  error_rate: number
  estimated_cost_usd: number
  requests_change_pct: number
  tokens_change_pct: number
  sessions_change_pct: number
  error_rate_change_pct: number
  cost_change_pct: number
  /** Org-level completeness rollup for the period. */
  completeness: BucketCompleteness
  /** Per-KPI partial flags when underlying buckets are incomplete. */
  partial_fields: Array<
    | "total_requests"
    | "total_tokens"
    | "total_sessions"
    | "error_rate"
    | "estimated_cost_usd"
  >
  model_distribution: ModelDistribution
  top_agents: TopAgentRow[]
  series: TimeBucket[]
}

export type LatencyStage =
  | "proxy_overhead"
  | "context_assembly"
  | "auth_validation"
  | "rate_limit_check"
  | "provider_latency"

export type LatencyPercentiles = {
  stage: LatencyStage
  p50: number
  p95: number
  p99: number
  /** Optional target ms from SLO / benchmark convention. */
  target_p95_ms: number | null
}

export type SlowRequest = {
  trace_id: string
  total_latency_ms: number
  provider_latency_ms: number
  context_assembly_ms: number
  timestamp: string
  agent_slug: string
}

export type AnalyticsLatency = {
  period: AnalyticsPeriod
  stages: LatencyPercentiles[]
  slow_requests: SlowRequest[]
  completeness: BucketCompleteness
}

export type RetrievalStats = {
  total_retrievals: number
  avg_memories_per_request: number
  avg_retrieval_latency_ms: number
  cache_hit_rate: number
  empty_result_rate: number
}

export type QualityStats = {
  avg_relevance_score: number
  positive_feedback_rate: number
  negative_feedback_rate: number
}

export type TopRetrievedMemory = {
  memory_id: string
  content_preview: string
  retrieval_count: number
  avg_score: number
}

export type AnalyticsMemoryPerformance = {
  period: AnalyticsPeriod
  retrieval_stats: RetrievalStats
  quality_stats: QualityStats
  top_retrieved_memories: TopRetrievedMemory[]
  completeness: BucketCompleteness
}

export type AnalyticsErrorKind = "endpoint_failed" | "forbidden" | "empty"

export type AnalyticsQuery = {
  period: AnalyticsPeriod
  agentIds: string[]
}
