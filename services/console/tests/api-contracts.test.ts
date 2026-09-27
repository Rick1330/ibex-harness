import { describe, expect, it } from "vitest"

import {
  OperatorContextSchema,
  OperatorOverviewSchema,
  OperatorTraceListSchema,
  parseOperatorSession,
  parsePlatformHealth,
} from "../src/lib/api/contracts"

const session = {
  subject: "user-1",
  org_id: "11111111-1111-4111-8111-111111111111",
  session_id: "session-1",
  permissions: 4,
}

const health = {
  dependency_health: { api: "ok", postgres: "ok", auth: "ok", redis: "ok" },
  last_backup_at: null,
  last_restore_drill: null,
  retention_horizon_days: 90,
  ingestion_lag_seconds: null,
  dlq_depth: 0,
  degraded_mode: false,
  outbox_max_aggregate_seq: 12,
  deploy_image_digest: "sha256:abc",
  observed_at: "2026-09-26T12:00:00.000Z",
}

const context = {
  schema_version: "operator.context.v1",
  org_id: session.org_id,
  role: "admin",
  org_name: "Example",
  org_slug: "example",
  org_status: "active",
  observed_at: "2026-09-26T12:00:00.000Z",
}

const overview = {
  schema_version: "operator.overview.v1",
  org_id: session.org_id,
  org_name: "Example",
  org_slug: "example",
  org_status: "active",
  counts: { active_users: 3, agents: 7, active_agents: 4 },
  observed_at: "2026-09-26T12:00:00.000Z",
  completeness: "complete",
}

const traceList = {
  schema_version: "operator.trace-list.v1",
  items: [{
    trace_id: "trace-a",
    run_id: "11111111-1111-4111-8111-111111111111",
    request_id: "request-a",
    agent_id: null,
    session_id: null,
    checkpoint_id: null,
    status: "ok",
    error_code: null,
    started_at: "2026-09-26T12:00:00.000Z",
    ended_at: "2026-09-26T12:00:01.000Z",
    duration_ms: 1000,
    evidence: {
      schema_version: "evidence.v1",
      capture_mode: "metadata",
      completeness: "partial",
      sample_decision: "kept",
      freshness: "unknown",
      retention: "unknown",
      source: "postgres.evidence_runs",
      source_watermark: "not_provided",
      observed_at: "2026-09-26T12:00:02.000Z",
    },
  }],
  next_cursor: null,
  truncated: false,
  observed_at: "2026-09-26T12:00:02.000Z",
  query_start: "2026-09-26T11:00:00.000Z",
  query_end: "2026-09-26T12:00:00.000Z",
  limit: 50,
}

describe("operator response contracts", () => {
  it("accepts the stable session and health shapes", () => {
    expect(parseOperatorSession(session).org_id).toBe(session.org_id)
    expect(parsePlatformHealth(health).dependency_health.redis).toBe("ok")
  })

  it("accepts versioned D1 DTOs and rejects secrets or unsupported metrics", () => {
    expect(OperatorContextSchema.parse(context).role).toBe("admin")
    expect(OperatorOverviewSchema.parse(overview).counts.active_agents).toBe(4)
    expect(() => OperatorContextSchema.parse({ ...context, access_token: "secret" })).toThrow()
    expect(() => OperatorOverviewSchema.parse({ ...overview, estimated_cost_usd: 0 })).toThrow()
  })

  it("rejects unknown session fields", () => {
    expect(() => parseOperatorSession({ ...session, token: "secret" })).toThrow()
  })

  it("rejects malformed tenant identity and health timestamps", () => {
    expect(() => parseOperatorSession({ ...session, org_id: "org-a" })).toThrow()
    expect(() => parsePlatformHealth({ ...health, observed_at: "not-a-time" })).toThrow()
  })

  it("accepts metadata-only D2 state and rejects content-bearing or unknown fields", () => {
    expect(OperatorTraceListSchema.parse(traceList).items[0]?.evidence.source).toBe("postgres.evidence_runs")
    expect(() => OperatorTraceListSchema.parse({ ...traceList, prompt: "<script>alert(1)</script>" })).toThrow()
    expect(() => OperatorTraceListSchema.parse({ ...traceList, items: [{ ...traceList.items[0], evidence: { ...traceList.items[0].evidence, source_watermark: "guess" } }] })).toThrow()
  })
})
