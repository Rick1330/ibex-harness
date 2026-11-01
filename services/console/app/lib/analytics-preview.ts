/**
 * Recorded preview fixtures for the Analytics surface.
 *
 * `operator.analytics.usage.v1` is marked NEEDS-BACKEND in `shared/operator/surfaces.ts` and is not
 * served by the BFF. Every series below is a fixture, and ClickHouse-style projections are derived
 * rather than certified, so no figure here may be presented as billing or SLO evidence.
 */

export const ANALYTICS_USAGE_CONTRACT = "operator.analytics.usage.v1 [NEEDS-BACKEND]"

export const ANALYTICS_DERIVED_NOTE =
  "These are derived projections, not certified records. A projection can show a trend; it cannot prove billing, deletion, or audit completeness."

/* ------------------------------------------------------------------- series */

export type UsagePoint = {
  day: string
  requests: number
  spendUsd: number
  inputTokens: number
  outputTokens: number
  cachedTokens: number
  reasoningTokens: number
  /** End-to-end latency percentiles for the proxy path. */
  p50Ms: number
  p95Ms: number
  p99Ms: number
  /** Split of the p95 figure: what the platform itself adds. */
  proxyOverheadP95Ms: number
  contextAssemblyP95Ms: number
  providerP95Ms: number
  errors: number
  policyDenials: number
}

export const ANALYTICS_DAYS: UsagePoint[] = [
  { day: "2026-10-17", requests: 4120, spendUsd: 188.4, inputTokens: 9_120_000, outputTokens: 1_840_000, cachedTokens: 3_410_000, reasoningTokens: 220_000, p50Ms: 640, p95Ms: 1810, p99Ms: 2940, proxyOverheadP95Ms: 74, contextAssemblyP95Ms: 212, providerP95Ms: 1524, errors: 12, policyDenials: 3 },
  { day: "2026-10-18", requests: 4388, spendUsd: 201.75, inputTokens: 9_640_000, outputTokens: 1_970_000, cachedTokens: 3_620_000, reasoningTokens: 241_000, p50Ms: 651, p95Ms: 1842, p99Ms: 3010, proxyOverheadP95Ms: 76, contextAssemblyP95Ms: 218, providerP95Ms: 1548, errors: 9, policyDenials: 5 },
  { day: "2026-10-19", requests: 3102, spendUsd: 141.2, inputTokens: 6_880_000, outputTokens: 1_402_000, cachedTokens: 2_510_000, reasoningTokens: 168_000, p50Ms: 622, p95Ms: 1744, p99Ms: 2801, proxyOverheadP95Ms: 71, contextAssemblyP95Ms: 205, providerP95Ms: 1468, errors: 7, policyDenials: 2 },
  { day: "2026-10-20", requests: 5904, spendUsd: 288.9, inputTokens: 13_040_000, outputTokens: 2_688_000, cachedTokens: 4_120_000, reasoningTokens: 318_000, p50Ms: 712, p95Ms: 2104, p99Ms: 3488, proxyOverheadP95Ms: 82, contextAssemblyP95Ms: 244, providerP95Ms: 1778, errors: 21, policyDenials: 8 },
  { day: "2026-10-21", requests: 6488, spendUsd: 322.4, inputTokens: 14_320_000, outputTokens: 2_940_000, cachedTokens: 4_010_000, reasoningTokens: 356_000, p50Ms: 748, p95Ms: 2288, p99Ms: 3742, proxyOverheadP95Ms: 88, contextAssemblyP95Ms: 268, providerP95Ms: 1932, errors: 28, policyDenials: 11 },
  { day: "2026-10-22", requests: 6210, spendUsd: 311.05, inputTokens: 13_710_000, outputTokens: 2_812_000, cachedTokens: 3_980_000, reasoningTokens: 341_000, p50Ms: 739, p95Ms: 2231, p99Ms: 3688, proxyOverheadP95Ms: 86, contextAssemblyP95Ms: 261, providerP95Ms: 1884, errors: 24, policyDenials: 9 },
  { day: "2026-10-23", requests: 5844, spendUsd: 292.6, inputTokens: 12_880_000, outputTokens: 2_644_000, cachedTokens: 3_902_000, reasoningTokens: 302_000, p50Ms: 722, p95Ms: 2148, p99Ms: 3540, proxyOverheadP95Ms: 84, contextAssemblyP95Ms: 249, providerP95Ms: 1815, errors: 18, policyDenials: 6 },
  { day: "2026-10-24", requests: 6020, spendUsd: 299.85, inputTokens: 13_260_000, outputTokens: 2_710_000, cachedTokens: 3_944_000, reasoningTokens: 311_000, p50Ms: 728, p95Ms: 2172, p99Ms: 3588, proxyOverheadP95Ms: 85, contextAssemblyP95Ms: 252, providerP95Ms: 1835, errors: 16, policyDenials: 7 },
  { day: "2026-10-25", requests: 4402, spendUsd: 208.3, inputTokens: 9_702_000, outputTokens: 1_988_000, cachedTokens: 3_610_000, reasoningTokens: 228_000, p50Ms: 668, p95Ms: 1902, p99Ms: 3122, proxyOverheadP95Ms: 78, contextAssemblyP95Ms: 224, providerP95Ms: 1600, errors: 11, policyDenials: 4 },
  { day: "2026-10-26", requests: 3288, spendUsd: 152.9, inputTokens: 7_288_000, outputTokens: 1_492_000, cachedTokens: 2_740_000, reasoningTokens: 174_000, p50Ms: 634, p95Ms: 1788, p99Ms: 2884, proxyOverheadP95Ms: 73, contextAssemblyP95Ms: 209, providerP95Ms: 1506, errors: 8, policyDenials: 3 },
  { day: "2026-10-27", requests: 6712, spendUsd: 344.2, inputTokens: 14_840_000, outputTokens: 3_048_000, cachedTokens: 4_180_000, reasoningTokens: 388_000, p50Ms: 762, p95Ms: 2344, p99Ms: 3802, proxyOverheadP95Ms: 90, contextAssemblyP95Ms: 274, providerP95Ms: 1980, errors: 26, policyDenials: 12 },
  { day: "2026-10-28", requests: 7044, spendUsd: 368.75, inputTokens: 15_580_000, outputTokens: 3_204_000, cachedTokens: 4_244_000, reasoningTokens: 412_000, p50Ms: 781, p95Ms: 2418, p99Ms: 3944, proxyOverheadP95Ms: 94, contextAssemblyP95Ms: 288, providerP95Ms: 2036, errors: 31, policyDenials: 14 },
  { day: "2026-10-29", requests: 7388, spendUsd: 392.1, inputTokens: 16_320_000, outputTokens: 3_362_000, cachedTokens: 4_302_000, reasoningTokens: 438_000, p50Ms: 804, p95Ms: 2512, p99Ms: 4108, proxyOverheadP95Ms: 98, contextAssemblyP95Ms: 302, providerP95Ms: 2112, errors: 34, policyDenials: 16 },
  { day: "2026-10-30", requests: 5102, spendUsd: 271.4, inputTokens: 11_264_000, outputTokens: 2_318_000, cachedTokens: 3_102_000, reasoningTokens: 296_000, p50Ms: 771, p95Ms: 2388, p99Ms: 3902, proxyOverheadP95Ms: 96, contextAssemblyP95Ms: 291, providerP95Ms: 2001, errors: 22, policyDenials: 9 },
]

/* ------------------------------------------------------------------- ranges */

export type AnalyticsRange = "7d" | "14d" | "30d"

export const ANALYTICS_RANGES: AnalyticsRange[] = ["7d", "14d", "30d"]

export const ANALYTICS_RANGE_LABELS: Record<AnalyticsRange, string> = {
  "7d": "Last 7 days",
  "14d": "Last 14 days",
  "30d": "Last 30 days",
}

/**
 * The fixture set covers 14 days. A wider window is reported as the same 14 days plus an explicit
 * statement that older days are not recorded, rather than being back-filled with invented numbers.
 */
export function analyticsDays(range: AnalyticsRange): UsagePoint[] {
  const count = range === "7d" ? 7 : ANALYTICS_DAYS.length
  return ANALYTICS_DAYS.slice(-count)
}

export function analyticsRequestedDays(range: AnalyticsRange): number {
  return range === "7d" ? 7 : range === "14d" ? 14 : 30
}

/** True when the range asks for days the projection does not have. */
export function analyticsIsPartial(range: AnalyticsRange): boolean {
  return analyticsDays(range).length !== analyticsRequestedDays(range)
}

export function analyticsCoverageText(range: AnalyticsRange): string {
  const days = analyticsDays(range)
  const requested = analyticsRequestedDays(range)
  if (days.length === requested) return `${requested} recorded days, through 30 Oct 2026`
  return `Only ${days.length} of the ${requested} requested days are recorded. The older days are absent, not zero.`
}

/* ------------------------------------------------------------------ metrics */

export type MetricKey = "spendUsd" | "requests" | "inputTokens" | "outputTokens" | "cachedTokens" | "reasoningTokens"

export const METRIC_LABELS: Record<MetricKey, string> = {
  spendUsd: "Spend",
  requests: "Requests",
  inputTokens: "Input tokens",
  outputTokens: "Output tokens",
  cachedTokens: "Cached tokens",
  reasoningTokens: "Reasoning tokens",
}

export function formatMetric(key: MetricKey, value: number): string {
  if (key === "spendUsd") {
    return `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }
  if (key === "requests") return value.toLocaleString("en-US")
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}k`
  return String(value)
}

export function metricSeries(points: UsagePoint[], key: MetricKey): number[] {
  return points.map((point) => point[key])
}

export function metricTotal(points: UsagePoint[], key: MetricKey): number {
  return points.reduce((sum, point) => sum + point[key], 0)
}

/** Cache savings are reported as a ratio of input tokens served from cache. */
export function cacheHitPercent(points: UsagePoint[]): number {
  const input = metricTotal(points, "inputTokens")
  const cached = metricTotal(points, "cachedTokens")
  return input === 0 ? 0 : (cached / (input + cached)) * 100
}

/* ------------------------------------------------------------------ latency */

export type LatencyBand = {
  label: string
  /** Null when the projection only records this band's p95 split. */
  p50: number | null
  p95: number
  p99: number | null
  meaning: string
}

/**
 * Only end-to-end latency is measured across all three percentiles. The platform bands are recorded
 * as a p95 split of that figure, so their p50 and p99 are reported as missing rather than scaled
 * from a distribution shape nobody measured.
 */
export function latencyBands(points: UsagePoint[]): LatencyBand[] {
  const last = points.at(-1)
  if (!last) return []
  return [
    {
      label: "Proxy overhead",
      p50: null,
      p95: last.proxyOverheadP95Ms,
      p99: null,
      meaning: "What the proxy itself adds on the critical path, excluding any upstream call. Recorded as a p95 split only.",
    },
    {
      label: "Context assembly",
      p50: null,
      p95: last.contextAssemblyP95Ms,
      p99: null,
      meaning: "Budget calculation, retrieval, ranking and packing. Runs against a bounded deadline and returns partial context when it expires. Recorded as a p95 split only.",
    },
    {
      label: "Provider time",
      p50: null,
      p95: last.providerP95Ms,
      p99: null,
      meaning: "Time reported by the upstream model provider. Not attributable to this platform. Recorded as a p95 split only.",
    },
    {
      label: "End to end",
      p50: last.p50Ms,
      p95: last.p95Ms,
      p99: last.p99Ms,
      meaning: "Observed request latency including all of the above.",
    },
  ]
}

export function latencySeries(points: UsagePoint[], key: "p50Ms" | "p95Ms" | "p99Ms"): number[] {
  return points.map((point) => point[key])
}

/* --------------------------------------------------------------- breakdown */

export type Dimension = "provider" | "model" | "agent"

export const DIMENSION_LABELS: Record<Dimension, string> = {
  provider: "Provider",
  model: "Model",
  agent: "Agent",
}

export const DIMENSIONS = Object.keys(DIMENSION_LABELS) as Dimension[]

export type BreakdownRow = {
  name: string
  id: string
  /** Share of window spend, 0..100. The share is the fixture; amounts are derived from it. */
  spendSharePercent: number
  /** Share of window requests, 0..100. A cheap model can carry many requests and little spend. */
  requestSharePercent: number
  /** Change against the previous window of the same length. */
  deltaPercent: number | null
  /** Whether the split is derived from a projection or a certified record. */
  certainty: "derived" | "certified"
}

/** A row with the selected window's totals applied, so this panel reconciles with the usage panel. */
export type BreakdownSlice = BreakdownRow & { spendUsd: number; requests: number }

const BREAKDOWNS: Record<Dimension, BreakdownRow[]> = {
  provider: [
    { name: "Anthropic", id: "prov_anthropic", spendSharePercent: 58.2, requestSharePercent: 63.5, deltaPercent: 14.2, certainty: "derived" },
    { name: "OpenAI", id: "prov_openai", spendSharePercent: 28.8, requestSharePercent: 24.9, deltaPercent: -6.4, certainty: "derived" },
    { name: "Local vLLM", id: "prov_local", spendSharePercent: 10.2, requestSharePercent: 10.4, deltaPercent: 2.1, certainty: "derived" },
    { name: "Unattributed", id: "prov_unknown", spendSharePercent: 2.8, requestSharePercent: 1.2, deltaPercent: null, certainty: "derived" },
  ],
  model: [
    { name: "claude-sonnet-4", id: "mdl_sonnet", spendSharePercent: 43.3, requestSharePercent: 43.1, deltaPercent: 18.9, certainty: "derived" },
    { name: "claude-haiku-3.5", id: "mdl_haiku", spendSharePercent: 14.9, requestSharePercent: 20.4, deltaPercent: -3.2, certainty: "derived" },
    { name: "gpt-4.1", id: "mdl_gpt41", spendSharePercent: 28.8, requestSharePercent: 24.9, deltaPercent: -6.4, certainty: "derived" },
    { name: "qwen-coder", id: "mdl_qwen", spendSharePercent: 10.2, requestSharePercent: 10.4, deltaPercent: 2.1, certainty: "derived" },
    { name: "Unattributed", id: "mdl_unknown", spendSharePercent: 2.8, requestSharePercent: 1.2, deltaPercent: null, certainty: "derived" },
  ],
  agent: [
    { name: "Support triage", id: "ag_support_triage", spendSharePercent: 90.9, requestSharePercent: 92.5, deltaPercent: 22.4, certainty: "derived" },
    { name: "Billing assistant", id: "ag_billing_analyst", spendSharePercent: 8.4, requestSharePercent: 6.8, deltaPercent: -1.8, certainty: "derived" },
    { name: "Unattributed", id: "ag_unknown", spendSharePercent: 0.7, requestSharePercent: 0.7, deltaPercent: null, certainty: "derived" },
  ],
}

export function analyticsBreakdown(dimension: Dimension, points: UsagePoint[]): BreakdownSlice[] {
  const totalSpend = metricTotal(points, "spendUsd")
  const totalRequests = metricTotal(points, "requests")
  return BREAKDOWNS[dimension].map((row) => ({
    ...row,
    spendUsd: (row.spendSharePercent / 100) * totalSpend,
    requests: Math.round((row.requestSharePercent / 100) * totalRequests),
  }))
}

export function analyticsMovers(dimension: Dimension, points: UsagePoint[]): BreakdownSlice[] {
  return analyticsBreakdown(dimension, points)
    .filter((row) => row.deltaPercent !== null)
    .sort((left, right) => Math.abs(right.deltaPercent ?? 0) - Math.abs(left.deltaPercent ?? 0))
}

/** Total of the rows shown, used to prove the split adds back up to the window. */
export function breakdownSpendTotal(rows: BreakdownSlice[]): number {
  return rows.reduce((sum, row) => sum + row.spendUsd, 0)
}

/** Rows whose attribution is unknown — they must stay visible, never folded into "other" silently. */
export function breakdownUnattributed(rows: BreakdownSlice[]): BreakdownSlice[] {
  return rows.filter((row) => row.id.endsWith("_unknown"))
}

/* ------------------------------------------------------------------ errors */

export function analyticsErrorRate(points: UsagePoint[]): number {
  const requests = points.reduce((sum, point) => sum + point.requests, 0)
  const errors = points.reduce((sum, point) => sum + point.errors, 0)
  return requests === 0 ? 0 : (errors / requests) * 100
}

export function analyticsDenials(points: UsagePoint[]): number {
  return points.reduce((sum, point) => sum + point.policyDenials, 0)
}

export const ANALYTICS_STATUS_TEXT = {
  text: "Derived preview fixtures. The usage contract is not connected, so these trends cannot be used as billing or SLO evidence.",
  detail:
    "Every chart is a fixture series with the same shape as the projection it stands in for. Percentiles describe the last recorded day, not a measured window.",
}

export const ANALYTICS_SLO_PENDING =
  "No measured window and no certified samples, so no p99 figure on this page can be compared against an objective."

export const METRIC_KEYS = Object.keys(METRIC_LABELS) as MetricKey[]
