import type { OperatorTrace } from "~~/shared/operator/contracts"

export type CertificationTier =
  | "evidence"
  | "metadata"
  | "uncertified"
  | "unavailable"
  | "preview"

export type TierDisplay = {
  tier: CertificationTier
  label: string
  meaning: string
  partial: boolean
  detail?: string
}

export const CERTIFICATION_TIERS: Array<{
  tier: CertificationTier
  label: string
  meaning: string
  form: string
}> = [
  {
    tier: "evidence",
    label: "Evidence",
    meaning: "A certified evidence record exists for this value.",
    form: "Solid square; solid left rail in streams.",
  },
  {
    tier: "metadata",
    label: "Metadata",
    meaning: "Metadata is certified; payload content is not.",
    form: "Square split on the diagonal.",
  },
  {
    tier: "uncertified",
    label: "Uncertified",
    meaning: "Observed, but no evidence record backs it.",
    form: "Hollow square with a dashed edge.",
  },
  {
    tier: "unavailable",
    label: "Unavailable",
    meaning: "The API does not provide it; it is never estimated.",
    form: "45 degree hatch; no tier square.",
  },
  {
    tier: "preview",
    label: "Preview",
    meaning: "The surface is not wired to live data yet.",
    form: "Diagonal stripe band plus a Preview tag.",
  },
]

export function tierLabel(tier: CertificationTier): string {
  return CERTIFICATION_TIERS.find((entry) => entry.tier === tier)?.label ?? "Uncertified"
}

export function tierMeaning(tier: CertificationTier): string {
  return CERTIFICATION_TIERS.find((entry) => entry.tier === tier)?.meaning ?? ""
}

export function tierForTrace(trace: Pick<OperatorTrace, "evidence">): TierDisplay {
  const evidence = trace.evidence
  if (
    evidence.publication_state === "failed" ||
    evidence.publication_state === "poison" ||
    evidence.publication_state === "unavailable"
  ) {
    return {
      tier: "unavailable",
      label: "Unavailable",
      meaning: "Publication did not produce a usable evidence record.",
      partial: false,
      detail: `publication=${evidence.publication_state}`,
    }
  }

  const partial =
    evidence.completeness !== "complete" ||
    evidence.publication_state === "partial" ||
    evidence.publication_state === "pending"

  const certified = evidence.source === "postgres.evidence_runs"
  return {
    tier: certified ? "metadata" : "uncertified",
    label: certified ? (partial ? "Metadata · Partial" : "Metadata") : "Uncertified",
    meaning: certified
      ? "The evidence record is certified; payload content is not retained on this surface."
      : "Observed in a read response without an evidence record.",
    partial,
    detail: `completeness=${evidence.completeness} · publication=${evidence.publication_state}`,
  }
}

export function tierForSnapshot(detail: string): TierDisplay {
  return {
    tier: "uncertified",
    label: "Uncertified",
    meaning: "Observed in the operator API response; no evidence record is attached to this value.",
    partial: false,
    detail,
  }
}

export function isTierPartial(tier: TierDisplay): boolean {
  return tier.partial
}
