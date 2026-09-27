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
    completeness: z.enum(["complete", "partial", "sampled", "late", "redacted", "expired", "deleted", "simulated"]),
    sample_decision: z.string().min(1).max(32),
    freshness: z.enum(["fresh", "stale", "unknown"]),
    retention: z.enum(["active", "expired", "deleted", "unknown"]),
    source: z.literal("postgres.evidence_runs"),
    source_watermark: z.null(),
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
    items: z.array(OperatorTraceSchema).max(100),
    next_cursor: z.string().max(2048).nullable(),
    truncated: z.boolean(),
    observed_at: z.string().datetime({ offset: true }),
    query_start: z.string().datetime({ offset: true }),
    query_end: z.string().datetime({ offset: true }),
    limit: z.number().int().min(1).max(100),
  })
  .strict()

export const OperatorTraceDetailSchema = OperatorTraceSchema.extend({
  schema_version: z.literal("operator.trace-detail.v1"),
  unavailable_sections: z.array(z.enum(["spans", "candidates", "score_explanation", "directives", "tools", "content"])),
}).strict()

export type OperatorSession = z.infer<typeof OperatorSessionSchema>
export type PlatformHealth = z.infer<typeof PlatformHealthSchema>
export type OperatorContext = z.infer<typeof OperatorContextSchema>
export type OperatorOverview = z.infer<typeof OperatorOverviewSchema>
export type OperatorTrace = z.infer<typeof OperatorTraceSchema>
export type OperatorTraceList = z.infer<typeof OperatorTraceListSchema>
export type OperatorTraceDetail = z.infer<typeof OperatorTraceDetailSchema>

export function parseOperatorSession(value: unknown): OperatorSession {
  return OperatorSessionSchema.parse(value)
}

export function parsePlatformHealth(value: unknown): PlatformHealth {
  return PlatformHealthSchema.parse(value)
}
