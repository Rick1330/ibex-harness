import type {
  AnalyticsLatency,
  AnalyticsMemoryPerformance,
  AnalyticsOverview,
  AnalyticsPeriod,
  TimeBucket,
} from "./types"

function hoursFor(period: AnalyticsPeriod): number {
  if (period === "24h") return 24
  if (period === "7d") return 24 * 7
  if (period === "30d") return 24 * 30
  return 24 * 90
}

/** Sample every Nth hour for longer periods so the chart stays readable. */
function stepFor(period: AnalyticsPeriod): number {
  if (period === "24h") return 1
  if (period === "7d") return 3
  if (period === "30d") return 12
  return 24
}

function buildSeries(period: AnalyticsPeriod): TimeBucket[] {
  const hours = hoursFor(period)
  const step = stepFor(period)
  const end = Date.UTC(2026, 1, 11, 16, 0, 0)
  const rows: TimeBucket[] = []
  for (let h = hours - 1; h >= 0; h -= step) {
    const t = new Date(end - h * 3_600_000)
    const iso = t.toISOString().slice(0, 13) + ":00:00.000Z"
    const tod = t.getUTCHours()
    const base = 1800 + Math.sin(tod / 3.5) * 900 + (24 - (h % 24)) * 40
    const requests = Math.round(
      base * (period === "24h" ? 1 : 0.85 + (h % 7) * 0.02),
    )
    const tokens = requests * (38 + (h % 5) * 3)
    // Last two buckets partial — mirrors late-arriving ClickHouse facts.
    const completeness = h <= 1 ? ("partial" as const) : ("complete" as const)
    rows.push({ hour: iso, requests, tokens, completeness })
  }
  return rows
}

const BASE_OVERVIEW: Omit<AnalyticsOverview, "period" | "series"> = {
  total_requests: 1_284_092,
  total_tokens: 48_200_000,
  total_sessions: 8_431,
  total_memories_created: 12_908,
  error_rate: 0.018,
  estimated_cost_usd: 1_284.55,
  requests_change_pct: 12.4,
  tokens_change_pct: 8.1,
  sessions_change_pct: 5.2,
  error_rate_change_pct: -12.0,
  cost_change_pct: 9.4,
  completeness: "partial",
  partial_fields: ["total_requests", "total_tokens", "estimated_cost_usd"],
  model_distribution: {
    "gpt-4-turbo": 0.52,
    "gpt-3.5-turbo": 0.18,
    "claude-3-opus": 0.11,
    "claude-3-sonnet": 0.08,
    "gpt-4o": 0.05,
    "gemini-1.5-pro": 0.03,
    "mistral-large": 0.015,
    "llama-3-70b": 0.01,
    "command-r-plus": 0.005,
  },
  top_agents: [
    {
      agent_id: "agt_01h9support",
      name: "Support Agent",
      slug: "support-agent",
      request_count: 45_210,
      token_count: 12_400_000,
    },
    {
      agent_id: "agt_01h9billing",
      name: "billing-bot",
      slug: "billing-bot",
      request_count: 12_100,
      token_count: 3_100_000,
    },
    {
      agent_id: "agt_01h9docs",
      name: "docs-helper",
      slug: "docs-helper",
      request_count: 8_430,
      token_count: 1_900_000,
    },
    {
      agent_id: "agt_01h9triage",
      name: "triage",
      slug: "triage",
      request_count: 5_120,
      token_count: 1_100_000,
    },
    {
      agent_id: "agt_01h9sched",
      name: "scheduler",
      slug: "scheduler",
      request_count: 2_980,
      token_count: 600_000,
    },
  ],
}

const PERIOD_SCALE: Record<AnalyticsPeriod, number> = {
  "24h": 0.08,
  "7d": 0.35,
  "30d": 1,
  "90d": 2.4,
}

export function buildOverview(
  period: AnalyticsPeriod,
  agentIds: string[] = [],
): AnalyticsOverview {
  const scale = PERIOD_SCALE[period]
  let top = BASE_OVERVIEW.top_agents
  if (agentIds.length) {
    top = top.filter((a) => agentIds.includes(a.agent_id))
  }
  const agentScale = agentIds.length
    ? Math.max(0.12, top.reduce((s, a) => s + a.request_count, 0) / 45_210)
    : 1

  const series = buildSeries(period).map((b) => ({
    ...b,
    requests: Math.round(b.requests * agentScale),
    tokens: Math.round(b.tokens * agentScale),
  }))

  return {
    ...BASE_OVERVIEW,
    period,
    total_requests: Math.round(
      BASE_OVERVIEW.total_requests * scale * agentScale,
    ),
    total_tokens: Math.round(BASE_OVERVIEW.total_tokens * scale * agentScale),
    total_sessions: Math.round(
      BASE_OVERVIEW.total_sessions * scale * agentScale,
    ),
    total_memories_created: Math.round(
      BASE_OVERVIEW.total_memories_created * scale * agentScale,
    ),
    estimated_cost_usd: +(
      BASE_OVERVIEW.estimated_cost_usd *
      scale *
      agentScale
    ).toFixed(2),
    top_agents: top.map((a) => ({
      ...a,
      request_count: Math.round(a.request_count * scale),
      token_count: Math.round(a.token_count * scale),
    })),
    series,
  }
}

export const EMPTY_OVERVIEW: AnalyticsOverview = {
  period: "24h",
  total_requests: 0,
  total_tokens: 0,
  total_sessions: 0,
  total_memories_created: 0,
  error_rate: 0,
  estimated_cost_usd: 0,
  requests_change_pct: 0,
  tokens_change_pct: 0,
  sessions_change_pct: 0,
  error_rate_change_pct: 0,
  cost_change_pct: 0,
  completeness: "complete",
  partial_fields: [],
  model_distribution: {},
  top_agents: [],
  series: [],
}

export function buildLatency(period: AnalyticsPeriod): AnalyticsLatency {
  return {
    period,
    completeness: period === "24h" ? "partial" : "complete",
    stages: [
      {
        stage: "proxy_overhead",
        p50: 12,
        p95: 28,
        p99: 67,
        target_p95_ms: 40,
      },
      {
        stage: "context_assembly",
        p50: 35,
        p95: 52,
        p99: 89,
        target_p95_ms: 80,
      },
      {
        stage: "auth_validation",
        p50: 0.8,
        p95: 1.2,
        p99: 2,
        target_p95_ms: 5,
      },
      {
        stage: "rate_limit_check",
        p50: 1.1,
        p95: 2.4,
        p99: 4.8,
        target_p95_ms: 8,
      },
      {
        stage: "provider_latency",
        p50: 980,
        p95: 2100,
        p99: 4200,
        target_p95_ms: 2500,
      },
    ],
    slow_requests: [
      {
        trace_id: "trace_a91f7c",
        total_latency_ms: 4820,
        provider_latency_ms: 4100,
        context_assembly_ms: 420,
        timestamp: "2026-02-11T14:22:08.120Z",
        agent_slug: "support-agent",
      },
      {
        trace_id: "trace_b02e44",
        total_latency_ms: 3910,
        provider_latency_ms: 3400,
        context_assembly_ms: 280,
        timestamp: "2026-02-11T13:01:44.000Z",
        agent_slug: "billing-bot",
      },
      {
        trace_id: "trace_c77e01",
        total_latency_ms: 3540,
        provider_latency_ms: 2900,
        context_assembly_ms: 390,
        timestamp: "2026-02-11T11:18:02.000Z",
        agent_slug: "support-agent",
      },
      {
        trace_id: "trace_d12ab9",
        total_latency_ms: 3210,
        provider_latency_ms: 2700,
        context_assembly_ms: 310,
        timestamp: "2026-02-11T09:44:11.000Z",
        agent_slug: "docs-helper",
      },
    ],
  }
}

export function buildMemoryPerformance(
  period: AnalyticsPeriod,
): AnalyticsMemoryPerformance {
  return {
    period,
    completeness: "complete",
    retrieval_stats: {
      total_retrievals: Math.round(94_200 * PERIOD_SCALE[period]),
      avg_memories_per_request: 4.2,
      avg_retrieval_latency_ms: 48,
      cache_hit_rate: 0.71,
      empty_result_rate: 0.086,
    },
    quality_stats: {
      avg_relevance_score: 0.78,
      positive_feedback_rate: 0.64,
      negative_feedback_rate: 0.11,
    },
    top_retrieved_memories: [
      {
        memory_id: "mem_refund_policy",
        content_preview: "Refunds within 30 days require order_id + reason…",
        retrieval_count: 1840,
        avg_score: 0.91,
      },
      {
        memory_id: "mem_sla_tier",
        content_preview: "Enterprise SLA acknowledges within 15 minutes…",
        retrieval_count: 1290,
        avg_score: 0.87,
      },
      {
        memory_id: "mem_billing_retry",
        content_preview: "Retry invoice send after 429 with exponential…",
        retrieval_count: 980,
        avg_score: 0.84,
      },
      {
        memory_id: "mem_tone_calm",
        content_preview: "Prefer calm tone when user message contains…",
        retrieval_count: 760,
        avg_score: 0.79,
      },
    ],
  }
}

export const AGENT_FILTER_OPTIONS = BASE_OVERVIEW.top_agents.map((a) => ({
  id: a.agent_id,
  name: a.name,
  slug: a.slug,
}))

/** Empty-result rate above this gets amber warning treatment. */
export const EMPTY_RESULT_WARN_THRESHOLD = 0.05
