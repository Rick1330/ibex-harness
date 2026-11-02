import { z } from "zod"

/** Stable API error envelope shared by operator routes. */
export const ApiErrorSchema = z
  .object({
    error: z.object({
      code: z.string().min(1),
      message: z.string().min(1),
      request_id: z.string().min(1).optional(),
      docs_url: z.string().url().optional(),
    }),
  })
  .strict()

/** AuthService-derived session context; org_id is never accepted from URL state. */
export const OperatorSessionSchema = z
  .object({
    subject: z.string().min(1),
    org_id: z.string().uuid(),
    session_id: z.string().min(1),
    permissions: z.number().int().nonnegative(),
  })
  .strict()

export const PlatformHealthSchema = z
  .object({
    dependency_health: z.record(z.string(), z.enum(["ok", "degraded", "unavailable"])),
    last_backup_at: z.string().datetime({ offset: true }).nullable(),
    last_restore_drill: z.record(z.string(), z.unknown()).nullable(),
    retention_horizon_days: z.number().int().nonnegative(),
    ingestion_lag_seconds: z.number().nonnegative().nullable(),
    dlq_depth: z.number().int().nonnegative().nullable(),
    degraded_mode: z.boolean(),
    outbox_max_aggregate_seq: z.number().int().nonnegative().nullable(),
    deploy_image_digest: z.string().min(1).nullable(),
    observed_at: z.string().datetime({ offset: true }),
  })
  .strict()

export const OperatorContextSchema = z
  .object({
    schema_version: z.literal("operator.context.v1"),
    org_id: z.string().uuid(),
    role: z.enum(["owner", "admin", "member", "viewer"]).nullable(),
    org_name: z.string().min(1).max(200),
    org_slug: z.string().min(1).max(100),
    org_status: z.string().min(1).max(32),
    observed_at: z.string().datetime({ offset: true }),
  })
  .strict()

export const OperatorOverviewSchema = z
  .object({
    schema_version: z.literal("operator.overview.v1"),
    org_id: z.string().uuid(),
    org_name: z.string().min(1).max(200),
    org_slug: z.string().min(1).max(100),
    org_status: z.string().min(1).max(32),
    counts: z
      .object({
        active_users: z.number().int().nonnegative(),
        agents: z.number().int().nonnegative(),
        active_agents: z.number().int().nonnegative(),
      })
      .strict(),
    observed_at: z.string().datetime({ offset: true }),
    completeness: z.literal("complete"),
  })
  .strict()

const TraceEvidenceSchema = z
  .object({
    schema_version: z.string().min(1).max(64),
    capture_mode: z.string().min(1).max(32),
    completeness: z.enum(["complete", "partial", "sampled", "late", "redacted", "expired", "deleted", "simulated"]),
    sample_decision: z.string().min(1).max(32),
    freshness: z.enum(["fresh", "stale", "unknown"]),
    retention: z.enum(["expired", "deleted", "unknown"]),
    source: z.literal("postgres.evidence_runs"),
    source_watermark: z
      .string()
      .min(1)
      .max(128)
      .refine((value) => value === "not_provided" || /^outbox:\d+$/.test(value), {
        message: "source_watermark must be not_provided or outbox:<seq>",
      }),
    publication_state: z.enum(["published", "partial", "pending", "failed", "poison", "unavailable"]),
    ingestion_lag_ms: z.number().int().nonnegative().nullable(),
    policy_version: z.literal("operator.trace-read.v1"),
    observed_at: z.string().datetime({ offset: true }),
  })
  .strict()

export const OperatorTraceSchema = z
  .object({
    trace_id: z.string().min(1).max(256),
    run_id: z.string().uuid(),
    request_id: z.string().min(1).max(256),
    agent_id: z.string().uuid().nullable(),
    session_id: z.string().uuid().nullable(),
    checkpoint_id: z.string().uuid().nullable(),
    status: z.enum(["ok", "error"]),
    error_code: z.string().max(128).nullable(),
    started_at: z.string().datetime({ offset: true }),
    ended_at: z.string().datetime({ offset: true }).nullable(),
    duration_ms: z.number().int().nonnegative().nullable(),
    evidence: TraceEvidenceSchema,
  })
  .strict()

export const OperatorTraceListSchema = z
  .object({
    schema_version: z.literal("operator.trace-list.v1"),
    query_grammar_version: z.literal("operator.trace-query.v1"),
    items: z.array(OperatorTraceSchema).max(100),
    next_cursor: z.string().max(2048).nullable(),
    truncated: z.boolean(),
    matched_count: z.number().int().nonnegative().nullable(),
    returned_count: z.number().int().min(0).max(100),
    observed_at: z.string().datetime({ offset: true }),
    query_start: z.string().datetime({ offset: true }),
    query_end: z.string().datetime({ offset: true }),
    limit: z.number().int().min(1).max(100),
  })
  .strict()

const UnavailableSectionSchema = z.enum([
  "spans",
  "candidates",
  "score_explanation",
  "directives",
  "tools",
  "content",
  "events",
  "assembly",
])

const TraceSpanSchema = z
  .object({
    span_id: z.string().min(1).max(64),
    parent_span_id: z.string().max(64).nullable(),
    operation_kind: z.string().min(1).max(128),
    status: z.string().min(1).max(32),
    error_code: z.string().max(128).nullable(),
    started_at: z.string().datetime({ offset: true }),
    ended_at: z.string().datetime({ offset: true }).nullable(),
  })
  .strict()

const TraceAssemblySchema = z
  .object({
    budget_calculation_ms: z.number().int().nonnegative(),
    directive_load_ms: z.number().int().nonnegative(),
    hot_memory_retrieval_ms: z.number().int().nonnegative(),
    cold_memory_retrieval_ms: z.number().int().nonnegative(),
    ranking_ms: z.number().int().nonnegative(),
    packing_ms: z.number().int().nonnegative(),
    formatting_ms: z.number().int().nonnegative(),
    total_ms: z.number().int().nonnegative(),
    candidates_evaluated: z.number().int().nonnegative(),
  })
  .strict()

const TraceCandidateSchema = z
  .object({
    memory_id: z.string().uuid(),
    retrieval_rank: z.number().int().nonnegative(),
    final_rank: z.number().int().nonnegative().nullable(),
    delta_rank: z.number().int().nullable(),
    category: z.string().max(64).nullable(),
    token_estimate: z.number().int().nonnegative().nullable(),
    exclusion: z.string().min(1).max(32),
    score_schema: z.string().min(1).max(64),
    composite_score: z.number().nullable(),
  })
  .strict()

const TraceDirectiveSchema = z
  .object({
    directive_version_id: z.string().uuid().nullable(),
    content_hash: z.string().max(128).nullable(),
    schema_version: z.string().min(1).max(64),
  })
  .strict()

const TraceToolSchema = z
  .object({
    tool_name: z.string().min(1).max(128),
    status: z.string().min(1).max(32),
    error_code: z.string().max(128).nullable(),
    started_at: z.string().datetime({ offset: true }).nullable(),
    ended_at: z.string().datetime({ offset: true }).nullable(),
  })
  .strict()

export const OperatorTraceDetailSchema = OperatorTraceSchema.extend({
  schema_version: z.literal("operator.trace-detail.v1"),
  unavailable_sections: z.array(UnavailableSectionSchema),
  spans: z.array(TraceSpanSchema).max(500).default([]),
  assembly: TraceAssemblySchema.nullable().default(null),
  candidates: z.array(TraceCandidateSchema).max(500).default([]),
  directive: TraceDirectiveSchema.nullable().default(null),
  tools: z.array(TraceToolSchema).max(200).default([]),
  score_schema_note: z.string().max(256).nullable().default(null),
}).strict()

export const AgentStatusSchema = z.enum(["active", "paused", "suspended", "archived"])

/**
 * Public operator projection of an agent. org_id and free-form config are
 * deliberately absent: the browser has no tenant authority and no write path.
 */
export const OperatorAgentSchema = z
  .object({
    id: z.string().uuid(),
    slug: z.string().min(1).max(64).regex(/^[a-z0-9-]+$/),
    name: z.string().min(1).max(200),
    description: z.string().max(4096).nullable(),
    status: AgentStatusSchema,
    default_provider: z.string().min(1).max(64).nullable(),
    default_model: z.string().min(1).max(128).nullable(),
    tags: z.array(z.string().min(1).max(64)).max(32),
    total_sessions: z.number().int().nonnegative(),
    total_memories: z.number().int().nonnegative(),
    total_tokens_used: z.number().int().nonnegative(),
    last_active_at: z.string().datetime({ offset: true }).nullable(),
    created_at: z.string().datetime({ offset: true }),
    updated_at: z.string().datetime({ offset: true }),
  })
  .strict()

export const OperatorAgentPageSchema = z
  .object({
    data: z.array(OperatorAgentSchema).max(100),
    pagination: z
      .object({
        has_more: z.boolean(),
        next_cursor: z.string().max(2048).nullable(),
        prev_cursor: z.string().max(2048).nullable(),
        total_count: z.number().int().nonnegative().nullable(),
      })
      .strict(),
  })
  .strict()

export const MemoryStatusSchema = z.enum([
  "active",
  "superseded",
  "merged_into",
  "archived",
  "quarantined",
  "deleted",
])

export const MemoryCategorySchema = z.enum([
  "factual",
  "preference",
  "behavioral",
  "episodic",
  "procedural",
])

/**
 * Count Unicode code points, not UTF-16 units. Python's `len()` and Pydantic's
 * `max_length` both count code points, so a Zod `.max()` on a string would
 * reject values the API accepts as soon as a character is outside the BMP
 * (one emoji is two UTF-16 units). Keep both sides on the same measure.
 */
export function codePointLength(value: string): number {
  return Array.from(value).length
}

/** Metadata-only operator memory projection. Content, content hashes,
 * embeddings, org_id, and free-form metadata are deliberately absent.
 */
export const OperatorMemorySchema = z
  .object({
    id: z.string().uuid(),
    agent_id: z.string().uuid(),
    session_id: z.string().uuid().nullable(),
    category: MemoryCategorySchema,
    status: MemoryStatusSchema,
    source: z.enum(["extracted", "user_provided", "imported", "inferred"]),
    confidence: z.number().min(0).max(1),
    usefulness_score: z.number().min(0).max(1),
    content_tokens: z.number().int().nonnegative(),
    retrieval_count: z.number().int().nonnegative(),
    last_retrieved_at: z.string().datetime({ offset: true }).nullable(),
    pii_detected: z.boolean(),
    pii_redacted: z.boolean(),
    visibility: z.enum(["agent", "org", "session"]),
    pinned: z.boolean(),
    // API: MemoryTag = StringConstraints(min_length=1, max_length=64), code points.
    tags: z
      .array(
        z
          .string()
          .min(1)
          .refine((tag) => codePointLength(tag) <= 64, "tag must be at most 64 characters"),
      )
      .max(32),
    lifecycle_revision: z.number().int().positive(),
    tombstoned: z.boolean(),
    expires_at: z.string().datetime({ offset: true }).nullable(),
    valid_from: z.string().datetime({ offset: true }),
    valid_until: z.string().datetime({ offset: true }).nullable(),
    observed_at: z.string().datetime({ offset: true }),
    created_at: z.string().datetime({ offset: true }),
    updated_at: z.string().datetime({ offset: true }),
  })
  .strict()

export const OperatorMemoryPageSchema = z
  .object({
    data: z.array(OperatorMemorySchema).max(100),
    pagination: z
      .object({
        has_more: z.boolean(),
        next_cursor: z.string().max(2048).nullable(),
        prev_cursor: z.string().max(2048).nullable(),
        total_count: z.number().int().nonnegative().nullable(),
      })
      .strict(),
  })
  .strict()

export const SessionStatusSchema = z.enum(["active", "completed", "abandoned", "error"])

export const SessionEvidenceCompletenessSchema = z.enum([
  "complete",
  "partial",
  "sampled",
  "late",
  "redacted",
  "expired",
  "deleted",
  "simulated",
])

export const SessionEvidenceStatusSchema = z.enum(["ok", "error"])

export const SessionTurnEvidenceSchema = z
  .object({
    trace_id: z.string().min(1).max(256),
    run_id: z.string().uuid(),
    completeness: SessionEvidenceCompletenessSchema,
    status: SessionEvidenceStatusSchema,
    error_code: z.string().max(128).nullable(),
    started_at: z.string().datetime({ offset: true }),
    ended_at: z.string().datetime({ offset: true }).nullable(),
  })
  .strict()

// API: `Field(min_length=1, max_length=256)`, which Pydantic counts in code
// points. The proxy bounds the stored name at 256 bytes, so counting code
// points here can never be narrower than a name the proxy actually saves.
const OperatorModelNameSchema = z
  .string()
  .min(1)
  .refine((value) => codePointLength(value) <= 256, "model must be at most 256 characters")

export const OperatorSessionTurnSchema = z
  .object({
    id: z.string().uuid(),
    turn_index: z.number().int().nonnegative(),
    request_id: z.string().min(1).max(256),
    input_tokens: z.number().int().nonnegative(),
    output_tokens: z.number().int().nonnegative(),
    model: OperatorModelNameSchema,
    provider: z.string().min(1).max(64),
    latency_ms: z.number().int().nonnegative(),
    is_streaming: z.boolean(),
    is_complete: z.boolean(),
    created_at: z.string().datetime({ offset: true }),
    trace: SessionTurnEvidenceSchema.nullable(),
  })
  .strict()

/** Metadata-only session projection; message content and hashes are absent. */
export const OperatorSessionRecordSchema = z
  .object({
    id: z.string().uuid(),
    agent_id: z.string().uuid(),
    external_id: z.string().max(128).nullable(),
    status: SessionStatusSchema,
    model: OperatorModelNameSchema,
    provider: z.string().min(1).max(64),
    directive_version_id: z.string().uuid().nullable(),
    turn_count: z.number().int().nonnegative(),
    total_input_tokens: z.number().int().nonnegative(),
    total_output_tokens: z.number().int().nonnegative(),
    total_latency_ms: z.number().int().nonnegative(),
    last_extracted_turn: z.number().int().nonnegative(),
    lifecycle_revision: z.number().int().positive(),
    evidence_fence_version: z.number().int().positive(),
    created_at: z.string().datetime({ offset: true }),
    updated_at: z.string().datetime({ offset: true }),
    completed_at: z.string().datetime({ offset: true }).nullable(),
  })
  .strict()

export const OperatorSessionRecordDetailSchema = OperatorSessionRecordSchema.extend({
  turns: z.array(OperatorSessionTurnSchema).max(500),
  turns_truncated: z.boolean(),
}).strict()

export const OperatorSessionRecordPageSchema = z
  .object({
    data: z.array(OperatorSessionRecordSchema).max(100),
    pagination: z
      .object({
        has_more: z.boolean(),
        next_cursor: z.string().max(2048).nullable(),
        prev_cursor: z.string().max(2048).nullable(),
        total_count: z.number().int().nonnegative().nullable(),
      })
      .strict(),
  })
  .strict()

export type OperatorSessionRecord = z.infer<typeof OperatorSessionRecordSchema>
export type PlatformHealth = z.infer<typeof PlatformHealthSchema>
export type OperatorContext = z.infer<typeof OperatorContextSchema>
export type OperatorOverview = z.infer<typeof OperatorOverviewSchema>
export type OperatorTrace = z.infer<typeof OperatorTraceSchema>
export type OperatorTraceList = z.infer<typeof OperatorTraceListSchema>
export type OperatorTraceDetail = z.infer<typeof OperatorTraceDetailSchema>
export type AgentStatus = z.infer<typeof AgentStatusSchema>
export type OperatorAgent = z.infer<typeof OperatorAgentSchema>
export type OperatorAgentPage = z.infer<typeof OperatorAgentPageSchema>
export type MemoryStatus = z.infer<typeof MemoryStatusSchema>
export type MemoryCategory = z.infer<typeof MemoryCategorySchema>
export type OperatorMemory = z.infer<typeof OperatorMemorySchema>
export type OperatorMemoryPage = z.infer<typeof OperatorMemoryPageSchema>
export type SessionStatus = z.infer<typeof SessionStatusSchema>
export type OperatorSessionTurn = z.infer<typeof OperatorSessionTurnSchema>
export type SessionTurnEvidence = z.infer<typeof SessionTurnEvidenceSchema>
export type OperatorSession = z.infer<typeof OperatorSessionSchema>
export type OperatorSessionRecordDetail = z.infer<typeof OperatorSessionRecordDetailSchema>
export type OperatorSessionRecordPage = z.infer<typeof OperatorSessionRecordPageSchema>
export type UnavailableSection = z.infer<typeof UnavailableSectionSchema>

export function parseOperatorSession(value: unknown): OperatorSession {
  return OperatorSessionSchema.parse(value)
}

export function parsePlatformHealth(value: unknown): PlatformHealth {
  return PlatformHealthSchema.parse(value)
}

export const EvidenceRangeSchema = z.enum(["24h", "7d", "30d"])

/**
 * `operator.evidence.summary.v1`.
 *
 * Every field states a fact this API can read. Nothing here is a verdict: the
 * contract deliberately does not call a run "certified", because a run row holds
 * no digest of its own — the only digest in the plane is the per-event
 * `evidence_outbox.payload_digest`. Capture completeness and relay delivery are
 * separate axes and must be read separately.
 */
export const EvidenceCompletenessCountsSchema = z
  .object({
    complete: z.number().int().nonnegative(),
    partial: z.number().int().nonnegative(),
    sampled: z.number().int().nonnegative(),
    late: z.number().int().nonnegative(),
    redacted: z.number().int().nonnegative(),
    expired: z.number().int().nonnegative(),
    deleted: z.number().int().nonnegative(),
    simulated: z.number().int().nonnegative(),
  })
  .strict()

export const EvidenceStatusCountsSchema = z
  .object({
    ok: z.number().int().nonnegative(),
    error: z.number().int().nonnegative(),
  })
  .strict()

export const EvidenceDeliveryCountsSchema = z
  .object({
    pending: z.number().int().nonnegative(),
    in_flight: z.number().int().nonnegative(),
    delivered: z.number().int().nonnegative(),
    failed: z.number().int().nonnegative(),
    poison: z.number().int().nonnegative(),
  })
  .strict()

/**
 * The organization-wide capture policy plus a count of agent overrides. Agent
 * rows resolve per agent, so no single agent mode describes the organization.
 */
export const EvidenceCapturePolicySchema = z
  .object({
    mode: z.enum(["none", "metadata_only", "redacted", "full"]).nullable(),
    agent_overrides: z.number().int().nonnegative(),
  })
  .strict()

export const EvidenceLegalHoldSchema = z
  .object({
    active: z.boolean(),
    since: z.string().datetime({ offset: true }).nullable(),
  })
  .strict()

export const OperatorEvidenceSummarySchema = z
  .object({
    schema_version: z.literal("operator.evidence.summary.v1"),
    range: EvidenceRangeSchema,
    window_start: z.string().datetime({ offset: true }),
    window_end: z.string().datetime({ offset: true }),
    observed_at: z.string().datetime({ offset: true }),
    runs_total: z.number().int().nonnegative(),
    capture_complete_runs: z.number().int().nonnegative(),
    completeness: EvidenceCompletenessCountsSchema,
    statuses: EvidenceStatusCountsSchema,
    last_run_at: z.string().datetime({ offset: true }).nullable(),
    delivery: EvidenceDeliveryCountsSchema,
    oldest_unsettled_at: z.string().datetime({ offset: true }).nullable(),
    last_delivered_at: z.string().datetime({ offset: true }).nullable(),
    capture_policy: EvidenceCapturePolicySchema,
    legal_hold: EvidenceLegalHoldSchema,
  })
  .strict()

export type EvidenceRange = z.infer<typeof EvidenceRangeSchema>
export type EvidenceCompletenessCounts = z.infer<typeof EvidenceCompletenessCountsSchema>
export type EvidenceStatusCounts = z.infer<typeof EvidenceStatusCountsSchema>
export type EvidenceDeliveryCounts = z.infer<typeof EvidenceDeliveryCountsSchema>
export type EvidenceCapturePolicy = z.infer<typeof EvidenceCapturePolicySchema>
export type EvidenceLegalHold = z.infer<typeof EvidenceLegalHoldSchema>
export type OperatorEvidenceSummary = z.infer<typeof OperatorEvidenceSummarySchema>

export const DirectiveInjectionModeSchema = z.enum([
  "system_first",
  "system_append",
  "user_prepend",
])

export const DirectiveUsageRangeSchema = z.enum(["24h", "7d", "30d"])

/**
 * `operator.directives.versions.v1`.
 *
 * Metadata only. Instruction text is never part of this contract:
 * `content_digest` is a 12-character identity prefix so two versions can be told
 * apart, not a verifier for the content.
 */
export const OperatorDirectiveSummarySchema = z
  .object({
    id: z.string().uuid(),
    agent_id: z.string().uuid(),
    agent_name: z.string().min(1),
    agent_slug: z.string().min(1),
    is_active: z.boolean(),
    injection_mode: DirectiveInjectionModeSchema,
    active_version_num: z.number().int().positive().nullable(),
    version_count: z.number().int().nonnegative(),
    last_version_at: z.string().datetime({ offset: true }).nullable(),
    updated_at: z.string().datetime({ offset: true }),
  })
  .strict()

export const OperatorDirectiveVersionSchema = z
  .object({
    version_num: z.number().int().positive(),
    content_digest: z.string().min(1).max(64),
    content_bytes: z.number().int().positive(),
    created_by: z.string().uuid().nullable(),
    created_at: z.string().datetime({ offset: true }),
    is_live: z.boolean(),
  })
  .strict()

export const OperatorDirectiveUsageSchema = z
  .object({
    version_num: z.number().int().positive(),
    sessions: z.number().int().nonnegative(),
    last_session_at: z.string().datetime({ offset: true }).nullable(),
  })
  .strict()

export const OperatorDirectiveDetailSchema = OperatorDirectiveSummarySchema.extend({
  // The API returns the newest 200 versions plus the pointed version when it is
  // older, so 201 is the real ceiling; `versions_truncated` marks a partial view.
  versions: z.array(OperatorDirectiveVersionSchema).max(201),
  versions_truncated: z.boolean(),
  usage: z.array(OperatorDirectiveUsageSchema).max(201),
  usage_truncated: z.boolean(),
  usage_total_sessions: z.number().int().nonnegative(),
  usage_range: DirectiveUsageRangeSchema,
  usage_window_start: z.string().datetime({ offset: true }),
  observed_at: z.string().datetime({ offset: true }),
  active_version_missing: z.boolean(),
}).strict()

export const OperatorDirectivePageSchema = z
  .object({
    data: z.array(OperatorDirectiveSummarySchema).max(100),
    pagination: z
      .object({
        has_more: z.boolean(),
        next_cursor: z.string().nullable(),
        prev_cursor: z.string().nullable(),
        total_count: z.number().int().nonnegative().nullable(),
      })
      .strict(),
    observed_at: z.string().datetime({ offset: true }),
  })
  .strict()

export type OperatorDirectiveSummary = z.infer<typeof OperatorDirectiveSummarySchema>
export type OperatorDirectiveVersion = z.infer<typeof OperatorDirectiveVersionSchema>
export type OperatorDirectiveUsage = z.infer<typeof OperatorDirectiveUsageSchema>
export type OperatorDirectiveDetail = z.infer<typeof OperatorDirectiveDetailSchema>
export type OperatorDirectivePage = z.infer<typeof OperatorDirectivePageSchema>
export type DirectiveUsageRange = z.infer<typeof DirectiveUsageRangeSchema>

export const DeletionRangeSchema = z.enum(["24h", "7d", "30d"])
export const DeletionStoreSchema = z.enum(["postgres", "clickhouse", "redis", "objectstore"])
export const ReceiptStatusSchema = z.enum(["pending", "verified", "failed", "not_applicable"])
export const ErasureStatusSchema = z.enum([
  "pending",
  "running",
  "succeeded",
  "failed",
  "hold_blocked",
])

/**
 * `operator.evidence.deletions.v1`.
 *
 * Metadata only: no ledger payload, hold reason, or memory content is in the
 * contract. `audit.continuity_ok` is structural (no gaps, links match); content
 * verification belongs to the `privacy-audit-verify` CLI.
 */
export const OperatorEvidenceDeletionsSchema = z
  .object({
    schema_version: z.literal("operator.evidence.deletions.v1"),
    range: DeletionRangeSchema,
    window_start: z.string().datetime({ offset: true }),
    window_end: z.string().datetime({ offset: true }),
    observed_at: z.string().datetime({ offset: true }),
    tombstones: z
      .object({
        events: z
          .object({
            forgotten: z.number().int().nonnegative(),
            expired: z.number().int().nonnegative(),
            purged: z.number().int().nonnegative(),
          })
          .strict(),
        pending: z.number().int().nonnegative(),
        oldest_pending_at: z.string().datetime({ offset: true }).nullable(),
        last_event_at: z.string().datetime({ offset: true }).nullable(),
        tombstoned_memories: z.number().int().nonnegative(),
      })
      .strict(),
    erasures: z
      .object({
        pending: z.number().int().nonnegative(),
        running: z.number().int().nonnegative(),
        succeeded: z.number().int().nonnegative(),
        failed: z.number().int().nonnegative(),
        hold_blocked: z.number().int().nonnegative(),
      })
      .strict(),
    jobs: z
      .array(
        z
          .object({
            id: z.string().min(1),
            status: ErasureStatusSchema,
            created_at: z.string().datetime({ offset: true }),
            finished_at: z.string().datetime({ offset: true }).nullable(),
            receipts: z
              .array(
                z
                  .object({
                    store: DeletionStoreSchema,
                    status: ReceiptStatusSchema,
                    verified_absent_at: z.string().datetime({ offset: true }).nullable(),
                  })
                  .strict(),
              )
              .max(8),
          })
          .strict(),
      )
      .max(20),
    jobs_truncated: z.boolean(),
    audit: z
      .object({
        entries: z.number().int().nonnegative(),
        first_seq: z.number().int().positive().nullable(),
        last_seq: z.number().int().positive().nullable(),
        continuity_ok: z.boolean(),
        broken_at_seq: z.number().int().positive().nullable(),
        last_row_hash: z.string().min(1).nullable(),
      })
      .strict(),
  })
  .strict()

export type OperatorEvidenceDeletions = z.infer<typeof OperatorEvidenceDeletionsSchema>
export type DeletionStore = z.infer<typeof DeletionStoreSchema>
export type ReceiptStatus = z.infer<typeof ReceiptStatusSchema>
export type ErasureStatus = z.infer<typeof ErasureStatusSchema>
