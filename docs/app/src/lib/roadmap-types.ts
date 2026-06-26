export type MilestoneStatus = "completed" | "in-progress" | "planned";

export const PHASE_SLUGS = [
  "phase-0-foundation",
  "phase-1-core-platform",
  "phase-1-5-docs-site",
  "phase-2-single-provider",
  "phase-3-memory-engine",
  "phase-4-multi-provider",
  "phase-5-production-hardening",
] as const;

export type PhaseSlug = (typeof PHASE_SLUGS)[number];

const STATUS_BY_RAW: Record<string, MilestoneStatus> = {
  completed: "completed",
  complete: "completed",
  superseded: "completed",
  "in-progress": "in-progress",
  partial: "in-progress",
  planned: "planned",
};

export function isMilestonePage(slugs: string[] | undefined): boolean {
  return Boolean(slugs?.includes("milestones") && slugs.length >= 3);
}

export function getPhaseSlug(slugs: string[] | undefined): string | undefined {
  return slugs?.[0]?.startsWith("phase-") ? slugs[0] : undefined;
}

export function normalizeStatus(raw: string | undefined): MilestoneStatus | undefined {
  if (!raw) return undefined;
  return STATUS_BY_RAW[raw.toLowerCase()];
}
