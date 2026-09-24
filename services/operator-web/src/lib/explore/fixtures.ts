import type {
  FailureListItem,
  ScoreSchema,
  SessionListItem,
  TraceDetail,
  TraceListItem,
} from "./types"

/**
 * Finished-state fixture — score_schema v1_full.
 * Five-term waterfall is the primary Explain UI after Track P unlock.
 */
export const FIXTURE_TRACE_FULL: TraceDetail = {
  trace_id: "trace_a91f7c",
  org: "Acme Corp",
  agent: "Support Agent",
  session_id: "session_88ac",
  request_id: "req_4e2b91",
  checkpoint_id: "ckpt_01h9",
  model: "gpt-4-turbo",
  provider: "openai",
  status: "success",
  started_at: "2026-02-11T14:22:08.120Z",
  latency: {
    auth_ms: 12,
    context_retrieve_ms: 180,
    provider_ms: 2100,
    stream_ms: 240,
    total_ms: 2840,
  },
  latency_full: {
    auth_ms: 12,
    rate_limit_ms: 4,
    context_retrieve_ms: 120,
    context_rank_ms: 40,
    context_pack_ms: 20,
    provider_ms: 2100,
    stream_ms: 240,
  },
  tokens: { prompt: 1240, completion: 602, total: 1842 },
  evidence: {
    completeness: "complete",
    sampled: false,
    freshness: "fresh",
    retention_days: 90,
  },
  reproducibility: {
    tokenizer_version: "v3",
    packing_policy_version: "v2",
    half_life_table_version: "v2024.06",
    directive_version: 12,
    directive_hash: "9f2a",
  },
  score_schema: "v1_full",
  spans: [
    {
      span_id: "sp_root",
      name: "proxy.chat",
      start_ms: 0,
      duration_ms: 2840,
      children: [
        {
          span_id: "sp_auth",
          name: "auth.validate",
          start_ms: 0,
          duration_ms: 12,
        },
        {
          span_id: "sp_rl",
          name: "rate_limit.check",
          start_ms: 12,
          duration_ms: 4,
        },
        {
          span_id: "sp_ctx",
          name: "context.assemble",
          start_ms: 16,
          duration_ms: 180,
          children: [
            {
              span_id: "sp_ret",
              name: "retrieval.search",
              start_ms: 16,
              duration_ms: 120,
              evidence_ref: "matrix",
            },
            {
              span_id: "sp_mem",
              name: "memory.read",
              start_ms: 40,
              duration_ms: 80,
            },
            {
              span_id: "sp_rank",
              name: "context.rank",
              start_ms: 136,
              duration_ms: 40,
              evidence_ref: "matrix",
            },
            {
              span_id: "sp_pack",
              name: "context.pack",
              start_ms: 176,
              duration_ms: 20,
              evidence_ref: "assembly",
            },
          ],
        },
        {
          span_id: "sp_prov",
          name: "provider.complete",
          start_ms: 196,
          duration_ms: 2100,
        },
        {
          span_id: "sp_tool",
          name: "tool.search",
          start_ms: 980,
          duration_ms: 420,
          evidence_ref: "tools",
        },
        {
          span_id: "sp_stream",
          name: "provider.stream",
          start_ms: 2296,
          duration_ms: 240,
        },
        {
          span_id: "sp_eval",
          name: "evaluation.score",
          start_ms: 2536,
          duration_ms: 80,
          evidence_ref: "evaluation",
        },
      ],
    },
  ],
  candidates: [
    {
      memory_id: "mem_01",
      retrieval_rank: 1,
      similarity: 0.91,
      final_rank: 1,
      delta_rank: 0,
      category: "procedural",
      token_estimate: 180,
      disposition: "included",
      score: {
        score_schema: "v1_full",
        composite: 0.87,
        terms: [
          {
            name: "relevance",
            raw: 0.95,
            weight: 0.4,
            contribution: 0.38,
            detail: "cosine=0.91 → calibrated 0.95",
          },
          {
            name: "recency",
            raw: 0.98,
            weight: 0.25,
            contribution: 0.245,
            detail: "days_since_access=3, half_life=180d → 0.98",
          },
          {
            name: "usefulness",
            raw: 0.8,
            weight: 0.2,
            contribution: 0.16,
            detail: "prior_accept_rate=0.80",
          },
          {
            name: "confidence",
            raw: 0.9,
            weight: 0.1,
            contribution: 0.09,
            detail: "extraction_conf=0.90",
          },
          {
            name: "frequency",
            raw: 0.6,
            weight: 0.05,
            contribution: 0.03,
            detail: "access_count_30d=12 → 0.60",
          },
        ],
      },
    },
    {
      memory_id: "mem_02",
      retrieval_rank: 2,
      similarity: 0.88,
      final_rank: 3,
      delta_rank: -1,
      category: "factual",
      token_estimate: 220,
      disposition: "budget_excluded",
      score: {
        score_schema: "v1_full",
        composite: 0.71,
        terms: [
          {
            name: "relevance",
            raw: 0.88,
            weight: 0.4,
            contribution: 0.352,
          },
          {
            name: "recency",
            raw: 0.72,
            weight: 0.25,
            contribution: 0.18,
            detail: "days_since_access=40, half_life=90d → 0.72",
          },
          {
            name: "usefulness",
            raw: 0.55,
            weight: 0.2,
            contribution: 0.11,
          },
          {
            name: "confidence",
            raw: 0.7,
            weight: 0.1,
            contribution: 0.07,
          },
          {
            name: "frequency",
            raw: 0.4,
            weight: 0.05,
            contribution: 0.02,
          },
        ],
      },
      edges: [
        {
          kind: "supersedes",
          other_memory_id: "mem_09",
          status: "resolved",
        },
      ],
    },
    {
      memory_id: "mem_03",
      retrieval_rank: 3,
      similarity: 0.84,
      final_rank: null,
      delta_rank: null,
      category: "preference",
      token_estimate: 95,
      disposition: "filtered",
      score: null,
      edges: [
        {
          kind: "contradicts",
          other_memory_id: "mem_11",
          status: "pending_review",
        },
      ],
    },
    {
      memory_id: "mem_04",
      retrieval_rank: 4,
      similarity: null,
      final_rank: null,
      delta_rank: null,
      category: null,
      token_estimate: null,
      disposition: "failed",
      score: null,
      error: "embedding_timeout",
    },
    {
      memory_id: "mem_05",
      retrieval_rank: 5,
      similarity: 0.79,
      final_rank: 2,
      delta_rank: 3,
      category: "behavioral",
      token_estimate: 140,
      disposition: "included",
      score: {
        score_schema: "v1_full",
        composite: 0.78,
        terms: [
          { name: "relevance", raw: 0.79, weight: 0.4, contribution: 0.316 },
          {
            name: "recency",
            raw: 0.9,
            weight: 0.25,
            contribution: 0.225,
            detail: "days_since_access=8, half_life=60d → 0.90",
          },
          { name: "usefulness", raw: 0.7, weight: 0.2, contribution: 0.14 },
          { name: "confidence", raw: 0.75, weight: 0.1, contribution: 0.075 },
          { name: "frequency", raw: 0.5, weight: 0.05, contribution: 0.025 },
        ],
      },
    },
    {
      memory_id: "mem_06",
      retrieval_rank: 6,
      similarity: 0.76,
      final_rank: 4,
      delta_rank: 2,
      category: "episodic",
      token_estimate: 210,
      disposition: "budget_excluded",
      score: {
        score_schema: "v1_full",
        composite: 0.64,
        terms: [
          { name: "relevance", raw: 0.76, weight: 0.4, contribution: 0.304 },
          {
            name: "recency",
            raw: 0.55,
            weight: 0.25,
            contribution: 0.1375,
            detail: "days_since_access=90, half_life=45d → 0.55",
          },
          { name: "usefulness", raw: 0.5, weight: 0.2, contribution: 0.1 },
          { name: "confidence", raw: 0.65, weight: 0.1, contribution: 0.065 },
          { name: "frequency", raw: 0.3, weight: 0.05, contribution: 0.015 },
        ],
      },
    },
    {
      memory_id: "mem_07",
      retrieval_rank: 7,
      similarity: 0.72,
      final_rank: null,
      delta_rank: null,
      category: "factual",
      token_estimate: 160,
      disposition: "filtered",
      score: null,
      edges: [
        {
          kind: "supersedes",
          other_memory_id: "mem_02",
          status: "resolved",
        },
      ],
    },
    {
      memory_id: "mem_08",
      retrieval_rank: 8,
      similarity: 0.7,
      final_rank: 5,
      delta_rank: 3,
      category: "preference",
      token_estimate: 88,
      disposition: "included",
      score: {
        score_schema: "v1_full",
        composite: 0.61,
        terms: [
          { name: "relevance", raw: 0.7, weight: 0.4, contribution: 0.28 },
          { name: "recency", raw: 0.85, weight: 0.25, contribution: 0.2125 },
          { name: "usefulness", raw: 0.4, weight: 0.2, contribution: 0.08 },
          { name: "confidence", raw: 0.6, weight: 0.1, contribution: 0.06 },
          { name: "frequency", raw: 0.2, weight: 0.05, contribution: 0.01 },
        ],
      },
    },
    {
      memory_id: "mem_09",
      retrieval_rank: 9,
      similarity: 0.68,
      final_rank: null,
      delta_rank: null,
      category: "procedural",
      token_estimate: 120,
      disposition: "budget_excluded",
      score: {
        score_schema: "v1_full",
        composite: 0.58,
        terms: [
          { name: "relevance", raw: 0.68, weight: 0.4, contribution: 0.272 },
          { name: "recency", raw: 0.7, weight: 0.25, contribution: 0.175 },
          { name: "usefulness", raw: 0.45, weight: 0.2, contribution: 0.09 },
          { name: "confidence", raw: 0.55, weight: 0.1, contribution: 0.055 },
          { name: "frequency", raw: 0.25, weight: 0.05, contribution: 0.0125 },
        ],
      },
    },
    {
      memory_id: "mem_10",
      retrieval_rank: 10,
      similarity: 0.65,
      final_rank: null,
      delta_rank: null,
      category: "behavioral",
      token_estimate: 100,
      disposition: "filtered",
      score: null,
      edges: [
        {
          kind: "contradicts",
          other_memory_id: "mem_05",
          status: "pending_review",
        },
      ],
    },
  ],
  context_assembly: {
    total_budget: 2000,
    tool_schema_tokens: 110,
    formatter_tokens: 30,
    buckets: [
      { label: "Directive", used: 420, budget: 2000, priority: 0 },
      { label: "History", used: 800, budget: 2000, priority: 1 },
      { label: "Memories", used: 640, budget: 2000, priority: 2 },
      { label: "Tool schemas", used: 140, budget: 2000, priority: 3 },
    ],
    compression: {
      memory_id: "mem_07",
      model: "summarizer-7b",
      tokens_before: 410,
      tokens_after: 96,
    },
  },
  directive: {
    version: 12,
    hash: "9f2a",
    current_active_version: 12,
    regression_test_status: "pass",
    scenarios_passed: 47,
    scenarios_total: 47,
    rollout: {
      stages: "10% → 50% → 100%",
      sticky_hash_bucket: 73,
      resolved_version: 12,
    },
  },
  routing: {
    primary_provider: "openai",
    primary_model: "gpt-4-turbo",
    reason: "directive route table · sticky session affinity",
    fallback_chain: [],
    circuit_breaker: "closed",
    sticky_hash_bucket: 73,
    rollout_stage: "100%",
    resolved_directive_version: 12,
  },
  tools: [
    {
      tool_name: "kb.search",
      idempotency_key: "idem_7c2a",
      args_sanitized: { query: "refund policy enterprise", top_k: 5 },
      result_summary: "3 hits · top=policy#refund-ent",
      latency_ms: 310,
      retry_count: 0,
      status: "ok",
    },
    {
      tool_name: "ticket.lookup",
      idempotency_key: "idem_9ab1",
      args_sanitized: { ticket_id: "T-44102" },
      result_summary: "status=open · priority=P2",
      latency_ms: 110,
      retry_count: 1,
      status: "ok",
    },
    {
      tool_name: "crm.get",
      idempotency_key: "idem_c4e0",
      args_sanitized: { account_id: "acc_9912", fields: ["plan", "seats"] },
      result_summary: "plan=enterprise · seats=240",
      latency_ms: 88,
      retry_count: 0,
      status: "ok",
    },
    {
      tool_name: "refund.quote",
      idempotency_key: "idem_d12f",
      args_sanitized: { order_id: "ord_7701", currency: "USD" },
      result_summary: "eligible · amount=128.40",
      latency_ms: 142,
      retry_count: 0,
      status: "ok",
    },
    {
      tool_name: "kb.search",
      idempotency_key: "idem_e88a",
      args_sanitized: { query: "SLA credit policy", top_k: 3 },
      result_summary: "2 hits · top=policy#sla-credit",
      latency_ms: 205,
      retry_count: 0,
      status: "ok",
    },
    {
      tool_name: "notify.slack",
      idempotency_key: "idem_f01b",
      args_sanitized: { channel: "#support-esc", text: "[redacted]" },
      result_summary: "delivered",
      latency_ms: 64,
      retry_count: 0,
      status: "ok",
    },
  ],
  evaluation: {
    scenario_id: "scenario#14",
    mode: "structured_judge",
    judge_model: "claude-3-opus",
    result: "PASS",
    rationale:
      "Response cites correct enterprise refund window and escalates P2.",
  },
  raw_available: true,
}

/**
 * Secondary finished fixture — also v1_full after Track P unlock.
 * Distinct trace id for nav/pinned demos (Δrank / budget paths).
 */
export const FIXTURE_TRACE_INTERIM: TraceDetail = {
  ...FIXTURE_TRACE_FULL,
  trace_id: "trace_b02e44",
  agent: "billing-bot",
  score_schema: "v1_full",
  status: "partial",
  latency: {
    ...FIXTURE_TRACE_FULL.latency,
    total_ms: 4120,
    provider_ms: 3200,
  },
}

const AGENTS = [
  "Support Agent",
  "billing-bot",
  "docs-helper",
  "triage",
  "scheduler",
] as const
const MODELS = [
  { model: "gpt-4-turbo", provider: "openai" },
  { model: "gpt-3.5-turbo", provider: "openai" },
  { model: "claude-3-opus", provider: "anthropic" },
] as const
const STATUSES = ["success", "error", "partial"] as const
const ERRORS = [
  "provider_timeout",
  "auth_rejected",
  "embedding_timeout",
  "rate_limited",
  "context_overflow",
] as const

function listFrom(t: TraceDetail): TraceListItem {
  return {
    trace_id: t.trace_id,
    agent: t.agent,
    session_id: t.session_id,
    model: t.model,
    provider: t.provider,
    status: t.status,
    latency: t.latency,
    tokens: {
      prompt: t.tokens.prompt,
      completion: t.tokens.completion,
    },
    evidence: t.evidence,
    started_at: t.started_at,
  }
}

function buildTraceList(): TraceListItem[] {
  const seed: TraceListItem[] = [
    listFrom(FIXTURE_TRACE_FULL),
    listFrom(FIXTURE_TRACE_INTERIM),
  ]
  const generated: TraceListItem[] = Array.from({ length: 46 }, (_, i) => {
    const n = i + 1
    const agent = AGENTS[n % AGENTS.length]
    const { model, provider } = MODELS[n % MODELS.length]
    const status = STATUSES[n % STATUSES.length]
    const auth = 6 + (n % 12)
    const context = 80 + (n % 20) * 12
    const providerMs = status === "error" ? 0 : 900 + (n % 15) * 110
    const stream = status === "error" ? 0 : 60 + (n % 10) * 18
    const prompt = 480 + (n % 25) * 40
    const completion = status === "error" ? 0 : 180 + (n % 18) * 22
    const hex = (0x100000 + n * 7919).toString(16).slice(0, 6)
    return {
      trace_id: `trace_${hex}`,
      agent,
      session_id: `session_${(0x8800 + (n % 28)).toString(16)}`,
      model,
      provider,
      status,
      latency: {
        auth_ms: auth,
        context_retrieve_ms: context,
        provider_ms: providerMs,
        stream_ms: stream,
        total_ms: auth + context + providerMs + stream + (n % 40),
      },
      tokens: { prompt, completion },
      evidence: {
        completeness:
          status === "error" ? "partial" : n % 7 === 0 ? "sampled" : "complete",
        sampled: n % 7 === 0 || status === "error",
        freshness: n % 11 === 0 ? "late" : "fresh",
        retention_days: n % 5 === 0 ? 30 : 90,
      },
      started_at: new Date(
        Date.parse("2026-02-11T14:22:08.000Z") - n * 7 * 60_000,
      ).toISOString(),
    }
  })
  return [...seed, ...generated]
}

function buildSessionList(): SessionListItem[] {
  return Array.from({ length: 24 }, (_, i) => {
    const agent = AGENTS[i % AGENTS.length]
    const { model } = MODELS[i % MODELS.length]
    const status = STATUSES[i % STATUSES.length]
    return {
      session_id: `session_${(0x8800 + i).toString(16)}`,
      agent,
      trace_count: 2 + (i % 17),
      status,
      last_active: new Date(
        Date.parse("2026-02-11T14:22:08.000Z") - i * 11 * 60_000,
      ).toISOString(),
      model,
    }
  })
}

function buildFailureList(): FailureListItem[] {
  return Array.from({ length: 22 }, (_, i) => {
    const agent = AGENTS[i % AGENTS.length]
    const { model } = MODELS[i % MODELS.length]
    const hex = (0x200000 + i * 4243).toString(16).slice(0, 6)
    return {
      trace_id: `trace_${hex}`,
      agent,
      error: ERRORS[i % ERRORS.length],
      model,
      started_at: new Date(
        Date.parse("2026-02-11T14:18:02.000Z") - i * 13 * 60_000,
      ).toISOString(),
    }
  })
}

export const TRACE_LIST: TraceListItem[] = buildTraceList()

export const SESSION_LIST: SessionListItem[] = buildSessionList()

export const FAILURE_LIST: FailureListItem[] = buildFailureList()

export const TRACE_BY_ID: Record<string, TraceDetail> = {
  [FIXTURE_TRACE_FULL.trace_id]: FIXTURE_TRACE_FULL,
  [FIXTURE_TRACE_INTERIM.trace_id]: FIXTURE_TRACE_INTERIM,
}

export const QUERY_SUGGESTIONS: Record<string, string[]> = {
  agent: ["Support Agent", "billing-bot", "docs-helper", "triage", "scheduler"],
  session: [
    "session_88ac",
    "session_12fe",
    "session_99bb",
    "session_a1c0",
    "session_b7e2",
  ],
  model: ["gpt-4-turbo", "gpt-3.5-turbo", "claude-3-opus"],
  provider: ["openai", "anthropic"],
  status: ["success", "error", "partial"],
  error: [
    "provider_timeout",
    "auth_rejected",
    "embedding_timeout",
    "rate_limited",
    "context_overflow",
  ],
  directive_version: ["12", "11", "10"],
  tool: ["kb.search", "ticket.lookup", "crm.get", "refund.quote"],
}

/** Gate: five-term waterfall only when contractually allowed. */
export function allowsFullWaterfall(schema: ScoreSchema): boolean {
  return schema === "v1_full"
}
