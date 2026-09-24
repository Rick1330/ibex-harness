/**
 * 4.D.3 Sessions / Memory / Safe Replay contracts.
 * Design fixtures only — privileged jobs stay gated until cascade/receipt/sandbox gates close.
 */

export type SessionStatus =
  | "initializing"
  | "active"
  | "suspended"
  | "resuming"
  | "completed"
  | "failed"
  | "abandoned"

export type TurnKind =
  | "inference_request"
  | "memory_read"
  | "tool_call"
  | "inference_response"
  | "checkpoint"
  | "missing"
  | "redacted"
  | "sampled"

export type MemoryLifecycle =
  "active" | "superseded" | "archived" | "quarantined" | "deleted"

export type MemoryCategory =
  "factual" | "preference" | "behavioral" | "episodic" | "procedural"

export type LineageKind = "supersedes" | "contradicts" | "specializes"

export type JobKind = "export" | "delete" | "replay"
export type JobStatus = "queued" | "running" | "completed" | "failed" | "parked"

export type StoreReceiptStatus =
  "verified" | "not_applicable" | "store_unreachable"

export type SessionListItem = {
  session_id: string
  agent: string
  status: SessionStatus
  turn_count: number
  duration_ms: number
  directive_version: number
  last_heartbeat_ago: string
  started_at: string
  tags: string[]
  model: string
}

export type InjectedMemory = {
  memory_id: string
  category: MemoryCategory
  retrieval_similarity: number
  composite_score: number
  final_rank: number
  components?: {
    relevance: number
    recency: number
    usefulness: number
    confidence: number
    frequency: number
  }
}

export type SessionTurn = {
  sequence_number: number
  kind: TurnKind
  at: string
  summary: string
  request_id?: string
  trace_id?: string
  model?: string
  tokens?: number
  latency_ms?: number
  tool_name?: string
  idempotent?: boolean
  memories?: InjectedMemory[]
  context_assembly?: {
    directive: number
    history: number
    memories: number
    tools: number
    budget: number
  }
  conversation_preview?: string
  checkpoint_id?: string
  /** Explicit event state — never an empty gap. */
  evidence_state?: "present" | "missing" | "redacted" | "sampled"
  directive_version?: number
  directive_hash?: string
}

export type SessionDetail = SessionListItem & {
  org: string
  turns: SessionTurn[]
  embedding_profile?: string
  embedding_mismatch?: boolean
}

export type LineageEdge = {
  kind: LineageKind
  direction: "from" | "to"
  memory_id: string
  status: MemoryLifecycle
  at?: string
  note?: string
}

export type MemoryListItem = {
  memory_id: string
  category: MemoryCategory
  preview: string
  confidence: number
  usefulness: number
  lifecycle: MemoryLifecycle
  visibility: string
  retrieved_in_sessions: number
  avg_composite: number
  updated_at: string
}

export type MemoryDetail = MemoryListItem & {
  content: string
  lineage: LineageEdge[]
  lineage_truncated: boolean
  embedding_model: string
  embedding_version: string
  current_embedding_version: string
  embedding_mismatch: boolean
  retrieval_note: string
}

export type CascadeStoreLine = {
  store: string
  detail: string
  rows_or_objects: number
  unit: string
  ok: boolean
}

export type CascadePreview = {
  target_label: string
  target_id: string
  kind: JobKind
  stores: CascadeStoreLine[]
  legal_hold: "none" | "active"
  legal_hold_note: string
}

export type StoreReceipt = {
  store: string
  status: StoreReceiptStatus
  detail: string
}

export type GovernedJob = {
  job_id: string
  kind: JobKind
  target_id: string
  status: JobStatus
  created_at: string
  receipts?: StoreReceipt[]
  error?: string
}

export type ReplayDiff = {
  tokens_delta: number
  latency_delta_ms: number
  semantic_diff: boolean
  summary: string
}

export type ReplaySandboxState = {
  snapshot_at: string
  directive_version: number
  directive_hash: string
  model_version: string
  tokenizer_version: string
  packing_policy_version: string
  original: {
    tool: string
    tool_result: string
    tokens: number
    latency_ms: number
  }
  replayed: {
    tool: string
    mocked: boolean
    tool_result: string
    tokens: number
    latency_ms: number
  }
  diff: ReplayDiff
  audit_request_id: string
  original_request_id: string
}

/**
 * Track P unlock — privileged export/delete/replay are live once these are true.
 * Flip any gate back to false to restore honest "coming soon" disablement.
 */
export const PRIVILEGED_GATES = {
  cascade_preview_equals_execution: true,
  cross_store_receipts_wired: true,
  replay_sandbox_negative_tests_pass: true,
} as const

export function privilegedActionsEnabled() {
  return (
    PRIVILEGED_GATES.cascade_preview_equals_execution &&
    PRIVILEGED_GATES.cross_store_receipts_wired &&
    PRIVILEGED_GATES.replay_sandbox_negative_tests_pass
  )
}
