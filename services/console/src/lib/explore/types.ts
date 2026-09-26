/**
 * Explore + Trace Inspector contracts (4.D.2 finished-state target).
 *
 * Track P unlock: fixtures ship `score_schema: v1_full` with five-term weights
 * wired (F4-025/029). Explain-tree still keys off `score_schema` so an
 * interim payload cannot dishonestly render a waterfall.
 */

export type ScoreSchema = "interim_v1" | "v1_full"

export type TraceStatus = "success" | "error" | "partial"

/** Evidence-state contract — explicit on the wire, never inferred. */
export type EvidenceState =
  | "complete"
  | "partial"
  | "sampled"
  | "late"
  | "redacted"
  | "expired"
  | "deleted"
  | "simulated"

export type MemoryCategory =
  "factual" | "procedural" | "preference" | "behavioral" | "episodic"

/** Mutually exclusive — never encode Filtered as numeric zero. */
export type CandidateDisposition =
  "included" | "budget_excluded" | "filtered" | "failed"

export type QueryField =
  | "agent"
  | "session"
  | "model"
  | "provider"
  | "status"
  | "error"
  | "directive_version"
  | "tool"
  | "text"

export type QueryChip = {
  id: string
  field: QueryField
  value: string
}

export type TimePreset = "15m" | "1h" | "24h" | "7d" | "custom"

export type ExploreTab = "traces" | "sessions" | "failures"

export type LatencyStages = {
  auth_ms: number
  rate_limit_ms: number
  context_retrieve_ms: number
  context_rank_ms: number
  context_pack_ms: number
  provider_ms: number
  stream_ms: number
}

export type EvidenceBadges = {
  completeness: EvidenceState
  sampled: boolean
  freshness: "fresh" | "late" | "stale"
  retention_days: number | null
}

export type Reproducibility = {
  tokenizer_version: string
  packing_policy_version: string
  half_life_table_version: string
  directive_version: number
  directive_hash: string
}

export type ScoreTerm = {
  name: "relevance" | "recency" | "usefulness" | "confidence" | "frequency"
  raw: number
  weight: number
  contribution: number
  /** Human-readable inputs, e.g. "days_since_access=3, half_life=180d" */
  detail?: string
}

export type InterimScore = {
  score_schema: "interim_v1"
  relevance: number
  relevance_weight: number
  recency: number
  recency_weight: number
  composite: number
  detail?: string
}

export type FullScore = {
  score_schema: "v1_full"
  terms: ScoreTerm[]
  composite: number
}

export type CandidateScore = InterimScore | FullScore

export type ContradictionEdge = {
  kind: "supersedes" | "contradicts"
  other_memory_id: string
  status: "resolved" | "pending_review"
}

export type RetrievalCandidate = {
  memory_id: string
  retrieval_rank: number
  similarity: number | null
  final_rank: number | null
  delta_rank: number | null
  category: MemoryCategory | null
  score: CandidateScore | null
  token_estimate: number | null
  disposition: CandidateDisposition
  edges?: ContradictionEdge[]
  error?: string
}

export type SpanNode = {
  span_id: string
  name: string
  start_ms: number
  duration_ms: number
  children?: SpanNode[]
  /** Optional link into candidate matrix / explain tree */
  evidence_ref?: string
}

export type BudgetBucket = {
  label: string
  used: number
  budget: number
  /** Injection priority order index (lower = earlier) */
  priority: number
}

export type CompressionEvent = {
  memory_id: string
  model: string
  tokens_before: number
  tokens_after: number
}

export type ContextAssembly = {
  total_budget: number
  buckets: BudgetBucket[]
  /** Includes tool-schema/formatter cost (F4-028) */
  tool_schema_tokens: number
  formatter_tokens: number
  compression?: CompressionEvent
}

export type RoutingDecision = {
  primary_provider: string
  primary_model: string
  reason: string
  fallback_chain: string[]
  circuit_breaker: "closed" | "open" | "half_open"
  sticky_hash_bucket?: number
  rollout_stage?: string
  resolved_directive_version?: number
}

export type DirectiveContext = {
  version: number
  hash: string
  current_active_version: number
  regression_test_status?: "pass" | "fail" | "critical_fail" | "pending"
  scenarios_passed?: number
  scenarios_total?: number
  rollout?: {
    stages: string
    sticky_hash_bucket: number
    resolved_version: number
  }
}

export type ToolCall = {
  tool_name: string
  idempotency_key: string
  args_sanitized: Record<string, unknown>
  result_summary: string
  latency_ms: number
  retry_count: number
  status: "ok" | "error"
}

export type EvaluationLink = {
  scenario_id: string
  mode: "deterministic" | "structured_judge" | "freeform_judge"
  judge_model: string
  result: "PASS" | "FAIL" | "CRITICAL_FAIL"
  rationale: string
}

export type TraceListItem = {
  trace_id: string
  agent: string
  session_id: string
  model: string
  provider: string
  status: TraceStatus
  latency: Pick<
    LatencyStages,
    "auth_ms" | "context_retrieve_ms" | "provider_ms" | "stream_ms"
  > & { total_ms: number }
  tokens: { prompt: number; completion: number }
  evidence: EvidenceBadges
  started_at: string
}

export type TraceDetail = TraceListItem & {
  org: string
  request_id: string
  checkpoint_id: string
  latency_full: LatencyStages
  tokens: { prompt: number; completion: number; total: number }
  reproducibility: Reproducibility
  score_schema: ScoreSchema
  spans: SpanNode[]
  candidates: RetrievalCandidate[]
  context_assembly: ContextAssembly
  directive: DirectiveContext
  routing: RoutingDecision
  tools: ToolCall[]
  evaluation?: EvaluationLink
  raw_available: boolean
}

export type SessionListItem = {
  session_id: string
  agent: string
  trace_count: number
  status: TraceStatus
  last_active: string
  model: string
}

export type FailureListItem = {
  trace_id: string
  agent: string
  error: string
  model: string
  started_at: string
}
