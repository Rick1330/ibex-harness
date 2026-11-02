import { describe, expect, it } from "vitest"

import {
  OperatorAgentPageSchema,
  OperatorAgentSchema,
  OperatorContextSchema,
  OperatorDirectiveDetailSchema,
  OperatorDirectivePageSchema,
  OperatorEvidenceSummarySchema,
  OperatorMemoryPageSchema,
  OperatorMemorySchema,
  OperatorOverviewSchema,
  OperatorSessionRecordDetailSchema,
  OperatorSessionRecordPageSchema,
  OperatorSessionRecordSchema,
  OperatorSessionSchema,
  OperatorTraceDetailSchema,
  OperatorTraceListSchema,
  PlatformHealthSchema,
  parseOperatorSession,
} from "../shared/operator/contracts"

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
  query_grammar_version: "operator.trace-query.v1",
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
      publication_state: "unavailable",
      ingestion_lag_ms: null,
      policy_version: "operator.trace-read.v1",
      observed_at: "2026-09-26T12:00:02.000Z",
    },
  }],
  next_cursor: null,
  truncated: false,
  matched_count: 1,
  returned_count: 1,
  observed_at: "2026-09-26T12:00:02.000Z",
  query_start: "2026-09-26T11:00:00.000Z",
  query_end: "2026-09-26T12:00:00.000Z",
  limit: 50,
}

const traceDetail = {
  ...traceList.items[0],
  schema_version: "operator.trace-detail.v1",
  unavailable_sections: [
    "spans",
    "candidates",
    "score_explanation",
    "directives",
    "tools",
    "content",
    "events",
    "assembly",
  ],
  spans: [],
  assembly: null,
  candidates: [],
  directive: null,
  tools: [],
  score_schema_note: null,
}

const agent = {
  id: "33333333-3333-4333-8333-333333333333",
  slug: "support-agent",
  name: "Support Agent",
  description: null,
  status: "active" as const,
  default_provider: "openai",
  default_model: "gpt-4.1",
  tags: ["prod"],
  total_sessions: 1,
  total_memories: 2,
  total_tokens_used: 3,
  last_active_at: null,
  created_at: "2026-09-26T12:00:00.000Z",
  updated_at: "2026-09-26T12:00:00.000Z",
}

const agentPage = {
  data: [agent],
  pagination: { has_more: false, next_cursor: null, prev_cursor: null, total_count: 1 },
}

const memory = {
  id: "44444444-4444-4444-8444-444444444444",
  agent_id: "33333333-3333-4333-8333-333333333333",
  session_id: null,
  category: "factual" as const,
  status: "active" as const,
  source: "extracted" as const,
  confidence: 0.8,
  usefulness_score: 0.5,
  content_tokens: 12,
  retrieval_count: 3,
  last_retrieved_at: null,
  pii_detected: false,
  pii_redacted: false,
  visibility: "agent" as const,
  pinned: false,
  tags: ["support"],
  lifecycle_revision: 1,
  tombstoned: false,
  expires_at: null,
  valid_from: "2026-11-02T12:00:00.000Z",
  valid_until: null,
  observed_at: "2026-11-02T12:00:00.000Z",
  created_at: "2026-11-02T12:00:00.000Z",
  updated_at: "2026-11-02T12:00:00.000Z",
}

const memoryPage = {
  data: [memory],
  pagination: { has_more: false, next_cursor: null, prev_cursor: null, total_count: 1 },
}

describe("operator response contracts", () => {
const sessionTurn = {
  id: "55555555-5555-4555-8555-555555555555",
  turn_index: 0,
  request_id: "req-1",
  input_tokens: 10,
  output_tokens: 20,
  model: "gpt-4.1",
  provider: "openai",
  latency_ms: 100,
  is_streaming: false,
  is_complete: true,
  created_at: "2026-11-02T12:00:00.000Z",
  trace: {
    trace_id: "4bf92f3577b34da6a3ce929d0e0e4736",
    run_id: "66666666-6666-4666-8666-666666666666",
    completeness: "complete" as const,
    status: "ok" as const,
    error_code: null,
    started_at: "2026-11-02T12:00:00.000Z",
    ended_at: "2026-11-02T12:00:01.000Z",
  },
}

const operatorSession = {
  id: "77777777-7777-4777-8777-777777777777",
  agent_id: "33333333-3333-4333-8333-333333333333",
  external_id: "ext-1",
  status: "active" as const,
  model: "gpt-4.1",
  provider: "openai",
  directive_version_id: null,
  turn_count: 1,
  total_input_tokens: 10,
  total_output_tokens: 20,
  total_latency_ms: 100,
  last_extracted_turn: 0,
  lifecycle_revision: 1,
  evidence_fence_version: 1,
  created_at: "2026-11-02T12:00:00.000Z",
  updated_at: "2026-11-02T12:00:01.000Z",
  completed_at: null,
}

const sessionDetail = {
  ...operatorSession,
  turns: [sessionTurn],
  turns_truncated: false,
}

const sessionPage = {
  data: [operatorSession],
  pagination: { has_more: false, next_cursor: null, prev_cursor: null, total_count: 1 },
}

const directive = {
  id: "11111111-1111-4111-8111-111111111111",
  agent_id: "22222222-2222-4222-8222-222222222222",
  agent_name: "Support triage",
  agent_slug: "support-triage",
  is_active: true,
  injection_mode: "system_first" as const,
  active_version_num: 2,
  version_count: 3,
  last_version_at: "2026-11-01T12:00:00.000Z",
  updated_at: "2026-11-02T12:00:00.000Z",
}

const evidenceSummary = {
  schema_version: "operator.evidence.summary.v1" as const,
  range: "7d" as const,
  window_start: "2026-10-26T12:00:00.000Z",
  window_end: "2026-11-02T12:00:00.000Z",
  observed_at: "2026-11-02T12:00:00.000Z",
  runs_total: 18,
  capture_complete_runs: 14,
  completeness: {
    complete: 14,
    partial: 3,
    sampled: 1,
    late: 0,
    redacted: 0,
    expired: 0,
    deleted: 0,
    simulated: 0,
  },
  statuses: { ok: 16, error: 2 },
  last_run_at: "2026-11-02T11:55:00.000Z",
  delivery: { pending: 2, in_flight: 0, delivered: 15, failed: 0, poison: 1 },
  oldest_unsettled_at: "2026-11-02T11:30:00.000Z",
  last_delivered_at: "2026-11-02T11:58:00.000Z",
  capture_policy: { mode: "metadata_only" as const, agent_overrides: 0 },
  legal_hold: { active: false, since: null },
}

  it("accepts the stable session and health shapes", () => {
    expect(parseOperatorSession(session).org_id).toBe(session.org_id)
    expect(PlatformHealthSchema.parse(health).dependency_health.redis).toBe("ok")
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
    expect(() => OperatorSessionSchema.parse({ ...session, org_id: "org-a" })).toThrow()
    expect(() => PlatformHealthSchema.parse({ ...health, observed_at: "not-a-time" })).toThrow()
  })

  it("accepts metadata-only D2 state and rejects content-bearing or unknown fields", () => {
    expect(OperatorTraceListSchema.parse(traceList).items[0]?.evidence.source).toBe(
      "postgres.evidence_runs",
    )
    expect(OperatorTraceDetailSchema.parse(traceDetail).unavailable_sections).toContain("content")
    expect(() =>
      OperatorTraceListSchema.parse({ ...traceList, prompt: "<script>alert(1)</script>" }),
    ).toThrow()
    expect(() =>
      OperatorTraceListSchema.parse({
        ...traceList,
        items: [
          {
            ...traceList.items[0],
            evidence: { ...traceList.items[0].evidence, source_watermark: "guess" },
          },
        ],
      }),
    ).toThrow()
  })

  it("accepts the operator agent projection and page", () => {
    expect(OperatorAgentSchema.parse(agent).slug).toBe("support-agent")
    expect(OperatorAgentPageSchema.parse(agentPage).pagination.has_more).toBe(false)
  })

  it("rejects tenant authority, unsupported status, and malformed identity", () => {
    expect(() => OperatorAgentSchema.parse({ ...agent, org_id: session.org_id })).toThrow()
    expect(() => OperatorAgentSchema.parse({ ...agent, status: "draining" })).toThrow()
    expect(() => OperatorAgentSchema.parse({ ...agent, id: "agent-1" })).toThrow()
    expect(() => OperatorAgentSchema.parse({ ...agent, slug: "Support Agent" })).toThrow()
  })

  it("rejects unknown pagination fields", () => {
    expect(() =>
      OperatorAgentPageSchema.parse({
        ...agentPage,
        pagination: { ...agentPage.pagination, cursor: "x" },
      }),
    ).toThrow()
  })

  it("accepts the metadata-only operator memory projection", () => {
    expect(OperatorMemorySchema.parse(memory).content_tokens).toBe(12)
    expect(OperatorMemoryPageSchema.parse(memoryPage).data[0]?.tags).toEqual(["support"])
  })

  it("rejects content, tenant authority, and malformed memory fields", () => {
    expect(() => OperatorMemorySchema.parse({ ...memory, content: "leak" })).toThrow()
    expect(() => OperatorMemorySchema.parse({ ...memory, org_id: session.org_id })).toThrow()
    expect(() => OperatorMemorySchema.parse({ ...memory, metadata: {} })).toThrow()
    expect(() => OperatorMemorySchema.parse({ ...memory, status: "draining" })).toThrow()
    expect(() => OperatorMemorySchema.parse({ ...memory, confidence: 1.5 })).toThrow()
  })

  it("accepts the metadata-only session projection, page, and turn trace", () => {
    expect(OperatorSessionRecordSchema.parse(operatorSession).turn_count).toBe(1)
    expect(OperatorSessionRecordPageSchema.parse(sessionPage).data).toHaveLength(1)
    const detail = OperatorSessionRecordDetailSchema.parse(sessionDetail)
    expect(detail.turns[0]?.trace?.trace_id).toBe(sessionTurn.trace.trace_id)
  })

  it("accepts a turn without evidence and rejects content or hashes", () => {
    const untraced = { ...sessionDetail, turns: [{ ...sessionTurn, trace: null }] }
    expect(OperatorSessionRecordDetailSchema.parse(untraced).turns[0]?.trace).toBeNull()
    expect(() => OperatorSessionRecordDetailSchema.parse({ ...sessionDetail, content: "leak" })).toThrow()
    expect(() =>
      OperatorSessionRecordDetailSchema.parse({ ...sessionDetail, messages_hash: "hash" }),
    ).toThrow()
    expect(() =>
      OperatorSessionRecordSchema.parse({ ...operatorSession, org_id: session.org_id }),
    ).toThrow()
    expect(() =>
      OperatorSessionRecordDetailSchema.parse({ ...sessionDetail, status: "deleted" }),
    ).toThrow()
    expect(() =>
      OperatorSessionRecordDetailSchema.parse({
        ...sessionDetail,
        turns: Array.from({ length: 501 }, () => sessionTurn),
      }),
    ).toThrow()
    expect(() =>
      OperatorSessionRecordDetailSchema.parse({
        ...sessionDetail,
        turns: [{ ...sessionTurn, trace: { ...sessionTurn.trace, status: "pending" } }],
      }),
    ).toThrow()
    expect(() =>
      OperatorSessionRecordDetailSchema.parse({
        ...sessionDetail,
        turns: [{ ...sessionTurn, request_id: "" }],
      }),
    ).toThrow()
    expect(() =>
      OperatorSessionRecordDetailSchema.parse({ ...sessionDetail, turns_truncated: "no" }),
    ).toThrow()
  })

  it("measures tag length in code points, like the API", () => {
    // Python len() and Pydantic max_length count code points; a 64-code-point
    // emoji tag is 128 UTF-16 units, so a naive .max(64) would reject a value
    // the API accepts and turn the list into a 502.
    const emojiTag = "🧠".repeat(64)
    expect(OperatorMemorySchema.parse({ ...memory, tags: [emojiTag] }).tags).toEqual([emojiTag])
    expect(() =>
      OperatorMemorySchema.parse({ ...memory, tags: ["🧠".repeat(65)] }),
    ).toThrow()
    expect(() =>
      OperatorMemorySchema.parse({ ...memory, tags: Array.from({ length: 33 }, () => "tag") }),
    ).toThrow()
  })

  it("accepts the model-name bound the proxy enforces", () => {
    // services/proxy validation.MaxModelNameLength is 256 bytes and the saved
    // value is passed through unchanged, so the projection must not be narrower.
    const model = "m".repeat(256)
    expect(OperatorSessionRecordSchema.parse({ ...operatorSession, model }).model).toHaveLength(256)
    expect(() => OperatorSessionRecordSchema.parse({ ...operatorSession, model: "m".repeat(257) })).toThrow()
    expect(() =>
      OperatorSessionRecordDetailSchema.parse({
        ...sessionDetail,
        turns: [{ ...sessionTurn, model }],
      }),
    ).not.toThrow()
  })

  it("accepts the directive contract and rejects instruction text", () => {
    const page = {
      data: [directive],
      pagination: { has_more: false, next_cursor: null, prev_cursor: null, total_count: 1 },
    }
    const detail = {
      ...directive,
      versions: [
        {
          version_num: 2,
          content_digest: "abcdef012345",
          content_bytes: 1024,
          created_by: null,
          created_at: "2026-10-30T12:00:00.000Z",
          is_live: true,
        },
      ],
      usage: [{ version_num: 2, sessions: 12, last_session_at: null }],
      usage_range: "7d",
      usage_window_start: "2026-10-26T12:00:00.000Z",
      active_version_missing: false,
    }

    expect(OperatorDirectivePageSchema.parse(page).data[0]?.active_version_num).toBe(2)
    const parsed = OperatorDirectiveDetailSchema.parse(detail)
    expect(parsed.versions[0]?.is_live).toBe(true)
    expect(parsed.usage[0]?.sessions).toBe(12)
    // Instruction text and an unknown range must not pass.
    expect(() =>
      OperatorDirectiveDetailSchema.parse({
        ...detail,
        versions: [{ ...detail.versions[0], content: "secret instruction" }],
      }),
    ).toThrow()
    expect(() => OperatorDirectiveDetailSchema.parse({ ...detail, usage_range: "90d" })).toThrow()
    expect(() => OperatorDirectivePageSchema.parse({ ...page, data: [{ ...directive, content: "x" }] })).toThrow()
  })

  it("accepts the evidence summary contract and rejects verdict language", () => {
    const parsed = OperatorEvidenceSummarySchema.parse(evidenceSummary)
    expect(parsed.capture_complete_runs).toBe(14)
    expect(parsed.completeness.complete).toBe(14)
    // Delivery is a separate axis: a complete capture with a poison row is legal.
    expect(parsed.delivery.poison).toBe(1)
    expect(() =>
      OperatorEvidenceSummarySchema.parse({ ...evidenceSummary, certified: true }),
    ).toThrow()
    expect(() =>
      OperatorEvidenceSummarySchema.parse({ ...evidenceSummary, range: "90d" }),
    ).toThrow()
    expect(() =>
      OperatorEvidenceSummarySchema.parse({
        ...evidenceSummary,
        completeness: { ...evidenceSummary.completeness, complete: -1 },
      }),
    ).toThrow()
    expect(() =>
      OperatorEvidenceSummarySchema.parse({
        ...evidenceSummary,
        capture_policy: { mode: "everything", agent_overrides: 0 },
      }),
    ).toThrow()
  })

  it("counts model-name length in code points, like the API", () => {
    // 256 code points outside the BMP are 512 UTF-16 units; the API accepts them
    // and a naive .max(256) would turn the session read into a 502.
    const model = "🧠".repeat(256)
    expect(OperatorSessionRecordSchema.parse({ ...operatorSession, model }).model).toBe(model)
    expect(() =>
      OperatorSessionRecordDetailSchema.parse({
        ...sessionDetail,
        turns: [{ ...sessionTurn, model }],
      }),
    ).not.toThrow()
    expect(() =>
      OperatorSessionRecordSchema.parse({ ...operatorSession, model: "🧠".repeat(257) }),
    ).toThrow()
  })
})
