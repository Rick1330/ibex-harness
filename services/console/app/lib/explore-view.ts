/**
 * Display vocabulary for the Explore surface.
 *
 * Every label here is keyed off a value that `operator.trace-list.v1` actually returns
 * (`~~/shared/operator/contracts`), so a new enum member is a type error rather than a silent
 * `humanize()` of an unknown string.
 */

import type { OperatorTrace, UnavailableSection } from "~~/shared/operator/contracts"

export type TraceStatus = OperatorTrace["status"]
export type TraceCompleteness = OperatorTrace["evidence"]["completeness"]
export type TracePublication = OperatorTrace["evidence"]["publication_state"]
export type TraceFreshness = OperatorTrace["evidence"]["freshness"]
export type TraceRetention = OperatorTrace["evidence"]["retention"]

export type { UnavailableSection }

export const EXPLORE_TRACE_LIST_CONTRACT = "operator.trace-list.v1"
export const EXPLORE_TRACE_DETAIL_CONTRACT = "operator.trace-detail.v1"
export const EXPLORE_QUERY_GRAMMAR = "operator.trace-query.v1"

export const TRACE_STATUS_LABELS: Record<TraceStatus, string> = {
  ok: "Completed",
  error: "Failed",
}

export const TRACE_STATUS_MEANING: Record<TraceStatus, string> = {
  ok: "The proxy reported no error for this run.",
  error: "The proxy or the provider reported an error for this run.",
}

export const COMPLETENESS_LABELS: Record<TraceCompleteness, string> = {
  complete: "Complete",
  partial: "Partial",
  sampled: "Sampled",
  late: "Late",
  redacted: "Redacted",
  expired: "Expired",
  deleted: "Deleted",
  simulated: "Simulated",
}

export const COMPLETENESS_MEANING: Record<TraceCompleteness, string> = {
  complete: "Every field this capture mode promises is present.",
  partial: "Some spans or fields are missing from the record.",
  sampled: "Only a sample of the run was captured; absence is expected.",
  late: "The record arrived after the collection window closed.",
  redacted: "Content was removed before storage. Metadata remains.",
  expired: "Retention has removed part or all of the record.",
  deleted: "A deletion request removed the underlying content.",
  simulated: "Produced by a simulated run, not live traffic.",
}

/** Completeness values where the record is not all there — these are what an operator scans for. */
export const ATTENTION_COMPLETENESS: TraceCompleteness[] = [
  "partial",
  "late",
  "redacted",
  "expired",
  "deleted",
]

export const PUBLICATION_LABELS: Record<TracePublication, string> = {
  published: "Published",
  partial: "Partially published",
  pending: "Pending",
  failed: "Failed",
  poison: "Poisoned",
  unavailable: "Not readable",
}

export const PUBLICATION_MEANING: Record<TracePublication, string> = {
  published: "The evidence row is fully written.",
  partial: "Some evidence rows for this run did not publish.",
  pending: "Publication has not finished yet.",
  failed: "Publication errored. The record may be missing downstream.",
  poison: "Publication produced an unusable row.",
  unavailable: "The publication state itself could not be read.",
}

/** Publication values that mean the evidence trail is broken, not merely young. */
export const BROKEN_PUBLICATION: TracePublication[] = ["failed", "poison", "unavailable"]

export const FRESHNESS_LABELS: Record<TraceFreshness, string> = {
  fresh: "Fresh",
  stale: "Stale",
  unknown: "Not reported",
}

export const FRESHNESS_MEANING: Record<TraceFreshness, string> = {
  fresh: "Read from the source inside this surface's freshness bound.",
  stale: "Older than the freshness bound for this surface.",
  unknown: "The source did not report a freshness signal.",
}

export const RETENTION_LABELS: Record<TraceRetention, string> = {
  expired: "Expired",
  deleted: "Deleted",
  unknown: "Not recorded",
}

export const RETENTION_MEANING: Record<TraceRetention, string> = {
  expired: "The retention window for this record has passed.",
  deleted: "A deletion has been applied to this record.",
  unknown: "The source did not report a retention state.",
}

export const SECTION_LABELS: Record<UnavailableSection, string> = {
  spans: "Span timings",
  candidates: "Retrieval candidates",
  score_explanation: "Score explanation",
  directives: "Directive version",
  tools: "Tool calls",
  content: "Prompt and completion",
  events: "Event stream",
  assembly: "Context assembly timings",
}

export const SECTION_MEANING: Record<UnavailableSection, string> = {
  spans: "No span rows were returned for this run, so no waterfall or per-operation timing exists.",
  candidates: "The candidate list was not returned, so ranking cannot be shown or reconstructed.",
  score_explanation: "The score schema did not include an explanation payload.",
  directives: "No directive version or content hash was attached to this run.",
  tools: "No tool-call rows were returned for this run.",
  content: "Prompt and completion text is never part of this contract. Absence here is a policy, not a gap.",
  events: "The event stream is not exposed through this contract.",
  assembly: "Context assembly stage timings were not returned for this run.",
}

export function isUnavailableSection(value: string): value is UnavailableSection {
  return Object.prototype.hasOwnProperty.call(SECTION_LABELS, value)
}

export function sectionLabel(value: string): string {
  return isUnavailableSection(value) ? SECTION_LABELS[value] : value
}

/**
 * The assembler's exclusion codes, as declared on the context wire contract
 * (`packages/proto/.../context.proto`, `MemoryUsed.exclusion`) and the evidence column default.
 * A code outside this set is shown exactly as returned rather than folded into one of these buckets.
 */
export type CandidateExclusion = "included" | "budget" | "filter" | "truncated" | "failed" | "unknown"

export const EXCLUSION_LABELS: Record<CandidateExclusion, string> = {
  included: "Packed",
  budget: "Budget",
  filter: "Filtered",
  truncated: "Truncated",
  failed: "Retrieval failed",
  unknown: "Unclassified",
}

export const EXCLUSION_MEANING: Record<CandidateExclusion, string> = {
  included: "The candidate survived packing and went into the assembled context.",
  budget: "Dropped because the remaining token budget could not hold it.",
  filter: "Dropped by a retrieval filter before packing was reached.",
  truncated: "Cut when the assembled context was truncated to fit.",
  failed: "Retrieval for this candidate errored.",
  unknown: "The assembler marked the candidate excluded without classifying why.",
}

const UNRECOGNISED_EXCLUSION = "The assembler returned this code as written; the console has no recorded meaning for it."

export function isCandidateExclusion(value: string): value is CandidateExclusion {
  return Object.prototype.hasOwnProperty.call(EXCLUSION_LABELS, value)
}

export function exclusionLabel(value: string): string {
  return isCandidateExclusion(value) ? EXCLUSION_LABELS[value] : value
}

export function exclusionMeaning(value: string): string {
  return isCandidateExclusion(value) ? EXCLUSION_MEANING[value] : UNRECOGNISED_EXCLUSION
}

/* ------------------------------------------------------------------ tones */

/** Text class for a completeness value. Semantic tokens only. */
export function completenessClass(value: TraceCompleteness): string {
  if (value === "complete") return "text-fg-1"
  if (value === "deleted" || value === "expired") return "text-crit"
  return "text-warn"
}

export function publicationClass(value: TracePublication): string {
  if (value === "published") return "text-fg-2"
  if (BROKEN_PUBLICATION.includes(value)) return "text-crit"
  return "text-warn"
}

export function freshnessClass(value: TraceFreshness): string {
  if (value === "fresh") return "text-fg-2"
  if (value === "stale") return "text-warn"
  return "text-fg-3"
}

/** `included` is the expected state; any other recorded code is something an operator scans for. */
export function exclusionClass(value: string): string {
  if (value === "included") return "text-fg-2"
  if (value === "failed") return "text-crit"
  return "text-warn"
}

/* --------------------------------------------------------------- summaries */

export type ExploreAttention = {
  errors: number
  incomplete: number
  brokenPublication: number
  sampled: number
}

export function exploreAttention(items: OperatorTrace[]): ExploreAttention {
  return items.reduce<ExploreAttention>(
    (totals, trace) => {
      if (trace.status === "error") totals.errors += 1
      if (ATTENTION_COMPLETENESS.includes(trace.evidence.completeness)) totals.incomplete += 1
      if (BROKEN_PUBLICATION.includes(trace.evidence.publication_state)) totals.brokenPublication += 1
      if (trace.evidence.completeness === "sampled") totals.sampled += 1
      return totals
    },
    { errors: 0, incomplete: 0, brokenPublication: 0, sampled: 0 },
  )
}

/** One sentence describing what the returned page does and does not prove. */
export function explorePageNote(itemCount: number, attention: ExploreAttention): string {
  if (itemCount === 0) return "No runs matched. An empty page is a valid answer, not a failure."
  const problems: string[] = []
  if (attention.errors > 0) problems.push(`${attention.errors} failed`)
  if (attention.incomplete > 0) problems.push(`${attention.incomplete} incomplete`)
  if (attention.brokenPublication > 0) problems.push(`${attention.brokenPublication} with broken publication`)
  if (problems.length === 0) {
    return `${itemCount} runs on this page, each with a complete record and a published evidence row.`
  }
  return `${itemCount} runs on this page: ${problems.join(", ")}.`
}

/**
 * The query language the contract supports. Anything outside this list is refused by the parser
 * rather than guessed at, so it is stated here instead of being invented as a facet.
 */
export const QUERY_FIELDS = [
  { field: "status", values: "ok · error", meaning: "Whether the run reported an error." },
  { field: "completeness", values: "complete · partial · sampled · late · redacted · expired · deleted · simulated", meaning: "How much of the record survived." },
  { field: "capture_mode", values: "as recorded by the proxy", meaning: "Which capture path produced the record." },
  { field: "trace / run / session", values: "an identifier", meaning: "Shorthands for trace_id, run_id and session_id." },
  { field: "request_id · error_code", values: "exact string", meaning: "Matched, not searched." },
  { field: "started_after · started_before", values: "ISO-8601", meaning: "Bounds the server applies before paging." },
  { field: "limit", values: "1–100", meaning: "Page size. Default 50." },
]

/** Copy for the About popover on each Explore surface, kept with the vocabulary it explains. */
export const EXPLORE_LIST_NOTES: { lead: string; body: string }[] = [
  {
    lead: "This page reads metadata, never content.",
    body: "Spans, prompts, completions and retrieved memories are not part of the list contract. A run with no span rows shows as unavailable rather than as a flat timeline.",
  },
  {
    lead: "A tier says what can be re-proved, not how good the run was.",
    body: "Metadata means the evidence row exists and can be re-read. Uncertified means the run was observed in a response without an evidence record behind it.",
  },
  {
    lead: "The query language is closed.",
    body: `${QUERY_FIELDS.map((entry) => entry.field).join(", ")} are the accepted fields. An unknown field is refused before anything is fetched, so a typo never becomes a silently wider search.`,
  },
]

export const EXPLORE_RUN_NOTES: { lead: string; body: string }[] = [
  {
    lead: "A section that is not returned stays empty.",
    body: "The detail contract names the sections it could not supply. Those render as unrecorded rather than being filled with a plausible shape, so an absent waterfall is never read as a fast run.",
  },
  {
    lead: "Span timings are the run's own record.",
    body: "The lenses re-read the same span rows in different arrangements. None of them computes a duration the proxy did not write, and a span with no end is drawn as open, not as instant.",
  },
  {
    lead: "Content is excluded by policy.",
    body: "Prompts, completions and retrieved memories are outside operator.trace-detail.v1. That is a standing rule of the contract, not a retention outcome for this run.",
  },
]

export const EXPLORE_TRACE_NOTES: { lead: string; body: string }[] = [
  {
    lead: "A trace is a grouping, not a verdict.",
    body: "Runs share a trace because the platform linked them. Whether each one succeeded is read from its own status and evidence row, never inferred from its neighbours.",
  },
  {
    lead: "The filter narrows what was returned.",
    body: "The trace query returns the runs it holds for this organization. Filtering happens over that set and is labelled as such, so a filtered count is never presented as a search result.",
  },
  {
    lead: "An empty trace is not a healthy trace.",
    body: "The identifier can resolve while no run metadata comes back. That is reported as unrecorded rather than as a run that did nothing.",
  },
]
