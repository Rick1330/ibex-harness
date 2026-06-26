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
  if (!slugs) return false;
  return slugs.includes("milestones") && slugs.length >= 3;
}

export function getPhaseSlug(slugs: string[] | undefined): string | undefined {
  if (!slugs || slugs.length === 0) return undefined;
  const first = slugs[0];
  return first.startsWith("phase-") ? first : undefined;
}

export function normalizeStatus(raw: string | undefined): MilestoneStatus | undefined {
  if (!raw) return undefined;
  return STATUS_BY_RAW[raw.trim().toLowerCase()];
}
