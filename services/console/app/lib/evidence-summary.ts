export type {
  EvidenceCapturePolicy,
  EvidenceCompletenessCounts,
  EvidenceDeliveryCounts,
  EvidenceLegalHold,
  EvidenceRange,
  EvidenceStatusCounts,
  OperatorEvidenceSummary,
} from "~~/shared/operator/contracts"

/**
 * Reading order for the completeness buckets, with a plain meaning for each.
 *
 * These are the values the `evidence_runs.completeness` CHECK constraint allows,
 * so the list is exhaustive by construction. `complete` is the only value that
 * claims the record holds the full capture; every other value names a reason it
 * does not, which is why the UI never folds them back into one "certified" badge.
 */
export const COMPLETENESS_ORDER = [
  "complete",
  "partial",
  "sampled",
  "late",
  "redacted",
  "expired",
  "deleted",
  "simulated",
] as const

export type CompletenessKey = (typeof COMPLETENESS_ORDER)[number]

export const COMPLETENESS_LABELS: Record<CompletenessKey, string> = {
  complete: "Complete",
  partial: "Partial",
  sampled: "Sampled",
  late: "Late",
  redacted: "Redacted",
  expired: "Expired",
  deleted: "Deleted",
  simulated: "Simulated",
}

export const COMPLETENESS_MEANING: Record<CompletenessKey, string> = {
  complete: "The record holds the full capture for the run.",
  partial: "Part of the capture is missing, and the record says so.",
  sampled: "Capture was sampled by decision; the window is not fully represented.",
  late: "The record arrived after the run finished.",
  redacted: "Fields were removed before storage. The metadata is still readable.",
  expired: "The retention window ended. The row is no longer a full record.",
  deleted: "The subject was deleted. The row records the deletion, not the payload.",
  simulated: "Recorded in a simulation, not against production traffic.",
}

export const COMPLETENESS_TONE: Record<CompletenessKey, "default" | "warning" | "critical" | "success"> = {
  complete: "success",
  partial: "warning",
  sampled: "warning",
  late: "warning",
  redacted: "default",
  expired: "default",
  deleted: "default",
  simulated: "warning",
}

export const DELIVERY_ORDER = ["delivered", "pending", "in_flight", "failed", "poison"] as const

export type DeliveryKey = (typeof DELIVERY_ORDER)[number]

export const DELIVERY_LABELS: Record<DeliveryKey, string> = {
  delivered: "Delivered",
  pending: "Pending",
  in_flight: "In flight",
  failed: "Failed",
  poison: "Poison",
}

export const DELIVERY_MEANING: Record<DeliveryKey, string> = {
  delivered: "The relay wrote the event to its sink.",
  pending: "Queued and not yet claimed by the relay.",
  in_flight: "Claimed by the relay and not yet acknowledged.",
  failed: "A delivery attempt failed; the relay will retry.",
  poison: "Repeated failure. The row needs an operator decision; it is not retried forever.",
}

export const DELIVERY_TONE: Record<DeliveryKey, "default" | "warning" | "critical" | "success"> = {
  delivered: "success",
  pending: "warning",
  in_flight: "default",
  failed: "warning",
  poison: "critical",
}

export function completenessTotal(counts: Record<CompletenessKey, number>): number {
  return COMPLETENESS_ORDER.reduce((sum, key) => sum + counts[key], 0)
}

export function deliveryTotal(counts: Record<DeliveryKey, number>): number {
  return DELIVERY_ORDER.reduce((sum, key) => sum + counts[key], 0)
}

export function unsettledDelivery(counts: Record<DeliveryKey, number>): number {
  return counts.pending + counts.in_flight + counts.failed + counts.poison
}
