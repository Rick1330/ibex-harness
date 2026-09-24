/**
 * Fixture client for /v1/analytics/* — shapes match the documented
 * ClickHouse-backed handlers. Permission gate: trace:read.
 */

import {
  EMPTY_OVERVIEW,
  buildLatency,
  buildMemoryPerformance,
  buildOverview,
} from "./fixtures"
import type {
  AnalyticsLatency,
  AnalyticsMemoryPerformance,
  AnalyticsOverview,
  AnalyticsPeriod,
  AnalyticsQuery,
} from "./types"

function delay(ms = 280) {
  return new Promise((r) => window.setTimeout(r, ms))
}

export class AnalyticsApiError extends Error {
  status: number
  code: "FORBIDDEN" | "ENDPOINT_FAILED"
  constructor(
    status: number,
    code: "FORBIDDEN" | "ENDPOINT_FAILED",
    message: string,
  ) {
    super(message)
    this.status = status
    this.code = code
  }
}

/** Demo toggles — flipped by the page view-state controls. */
let forceForbidden = false
let forceEmpty = false
let forceFail = false

export function setAnalyticsDemoFlags(flags: {
  forbidden?: boolean
  empty?: boolean
  fail?: boolean
}) {
  if (flags.forbidden != null) forceForbidden = flags.forbidden
  if (flags.empty != null) forceEmpty = flags.empty
  if (flags.fail != null) forceFail = flags.fail
}

function gate() {
  if (forceForbidden) {
    throw new AnalyticsApiError(
      403,
      "FORBIDDEN",
      "Missing permission trace:read",
    )
  }
  if (forceFail) {
    throw new AnalyticsApiError(
      503,
      "ENDPOINT_FAILED",
      "ClickHouse query timed out",
    )
  }
}

export async function getAnalyticsOverview(
  query: AnalyticsQuery,
): Promise<AnalyticsOverview> {
  await delay()
  gate()
  if (forceEmpty) return { ...EMPTY_OVERVIEW, period: query.period }
  return buildOverview(query.period, query.agentIds)
}

export async function getAnalyticsLatency(
  query: Pick<AnalyticsQuery, "period">,
): Promise<AnalyticsLatency> {
  await delay(220)
  gate()
  if (forceEmpty) {
    return {
      period: query.period,
      stages: [],
      slow_requests: [],
      completeness: "complete",
    }
  }
  return buildLatency(query.period)
}

export async function getAnalyticsMemoryPerformance(
  query: Pick<AnalyticsQuery, "period">,
): Promise<AnalyticsMemoryPerformance> {
  await delay(240)
  gate()
  if (forceEmpty) {
    return {
      period: query.period,
      retrieval_stats: {
        total_retrievals: 0,
        avg_memories_per_request: 0,
        avg_retrieval_latency_ms: 0,
        cache_hit_rate: 0,
        empty_result_rate: 0,
      },
      quality_stats: {
        avg_relevance_score: 0,
        positive_feedback_rate: 0,
        negative_feedback_rate: 0,
      },
      top_retrieved_memories: [],
      completeness: "complete",
    }
  }
  return buildMemoryPerformance(query.period)
}

export function periodLabel(p: AnalyticsPeriod) {
  return p
}
