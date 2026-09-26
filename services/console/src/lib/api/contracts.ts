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

export type OperatorSession = z.infer<typeof OperatorSessionSchema>
export type PlatformHealth = z.infer<typeof PlatformHealthSchema>
export type OperatorContext = z.infer<typeof OperatorContextSchema>
export type OperatorOverview = z.infer<typeof OperatorOverviewSchema>

export function parseOperatorSession(value: unknown): OperatorSession {
  return OperatorSessionSchema.parse(value)
}

export function parsePlatformHealth(value: unknown): PlatformHealth {
  return PlatformHealthSchema.parse(value)
}
