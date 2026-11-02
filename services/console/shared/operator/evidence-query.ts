/**
 * Shared live Evidence query codec for `operator.evidence.summary.v1`.
 *
 * The summary is a single window-scoped read, so the only state is the range and
 * the tab. Tabs are presentation: only `coverage` and `delivery` have data behind
 * them, and the other two say so rather than showing fixtures.
 */

import type { EvidenceRange } from "./contracts"

export const EVIDENCE_TABS = ["coverage", "delivery", "tombstones", "redaction"] as const
export type EvidenceTab = (typeof EVIDENCE_TABS)[number]

export const EVIDENCE_TAB_LABELS: Record<EvidenceTab, string> = {
  coverage: "Coverage",
  delivery: "Delivery",
  tombstones: "Tombstones",
  redaction: "Redaction",
}

export const EVIDENCE_RANGES: EvidenceRange[] = ["24h", "7d", "30d"]

export const EVIDENCE_RANGE_LABELS: Record<EvidenceRange, string> = {
  "24h": "Last 24 hours",
  "7d": "Last 7 days",
  "30d": "Last 30 days",
}

export type LiveEvidenceQuery = {
  tab: EvidenceTab
  range: EvidenceRange
}

type QueryParams = URLSearchParams | Record<string, unknown>

const ALLOWED = new Set(["tab", "range"])
const TABS = new Set<string>(EVIDENCE_TABS)
const RANGES = new Set<string>(EVIDENCE_RANGES)

export class LiveEvidenceQueryError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "LiveEvidenceQueryError"
  }
}

function paramGet(params: QueryParams, key: string): string | null {
  if (params instanceof URLSearchParams) return params.get(key)
  const raw = params[key]
  if (Array.isArray(raw)) return typeof raw[0] === "string" ? raw[0] : null
  return typeof raw === "string" ? raw : null
}

function parseTab(raw: string | null): EvidenceTab {
  if (raw == null || raw === "") return "coverage"
  if (TABS.has(raw)) return raw as EvidenceTab
  throw new LiveEvidenceQueryError("invalid evidence tab")
}

function parseRange(raw: string | null): EvidenceRange {
  if (raw == null || raw === "") return "24h"
  if (RANGES.has(raw)) return raw as EvidenceRange
  throw new LiveEvidenceQueryError("range must be one of 24h, 7d, 30d")
}

export function defaultLiveEvidenceQuery(): LiveEvidenceQuery {
  return { tab: "coverage", range: "24h" }
}

export function parseLiveEvidenceQuery(params: QueryParams): LiveEvidenceQuery {
  const keys = params instanceof URLSearchParams ? [...params.keys()] : Object.keys(params)
  for (const key of keys) {
    if (!ALLOWED.has(key)) throw new LiveEvidenceQueryError(`Unknown query field: ${key}`)
  }
  return {
    tab: parseTab(paramGet(params, "tab")),
    range: parseRange(paramGet(params, "range")),
  }
}

/**
 * Best-effort parse for a URL the operator did not construct. Keep the fields
 * that parse and drop the rest, so the page can rewrite the address bar to match
 * what it actually reads instead of widening or reinterpreting the request.
 */
export function parseLiveEvidenceQueryLenient(params: QueryParams): LiveEvidenceQuery {
  const field = <T>(read: () => T, fallback: T): T => {
    try {
      return read()
    } catch {
      return fallback
    }
  }
  return {
    tab: field(() => parseTab(paramGet(params, "tab")), "coverage"),
    range: field(() => parseRange(paramGet(params, "range")), "24h"),
  }
}

export function serializeLiveEvidenceQuery(query: LiveEvidenceQuery): URLSearchParams {
  const params = new URLSearchParams()
  params.set("range", query.range)
  if (query.tab !== "coverage") params.set("tab", query.tab)
  return params
}

export function liveEvidenceQueryKey(query: LiveEvidenceQuery): string {
  return serializeLiveEvidenceQuery(query).toString()
}

/**
 * The summary is window-scoped only. `tab` is presentation, so it must not
 * reach the upstream query model nor key the fetch — otherwise every tab switch
 * refetches an identical summary.
 */
export function evidenceSummaryParams(range: EvidenceRange): URLSearchParams {
  return new URLSearchParams({ range })
}

/** The deletion record behind a tombstone uses the same window as the summary. */
export function evidenceDeletionsParams(range: EvidenceRange): URLSearchParams {
  return new URLSearchParams({ range })
}
