import type { InferPageType } from "fumadocs-core/source";

import {
  PHASE_SLUGS,
  normalizeStatus,
  type MilestoneStatus,
  type PhaseSlug,
} from "@/lib/roadmap-types";
import { roadmapSource } from "@/lib/source";

export type RoadmapPage = InferPageType<typeof roadmapSource>;

export function getRoadmapPages() {
  return roadmapSource.getPages();
}

export function getMilestonePages() {
  return getRoadmapPages().filter((page) =>
    page.slugs.includes("milestones"),
  );
}

export function getPhaseIndexPage(slug: PhaseSlug) {
  return roadmapSource.getPage([slug]);
}

function countMilestoneStatuses(pages: RoadmapPage[]) {
  const counts = {
    completed: 0,
    "in-progress": 0,
    planned: 0,
  } satisfies Record<MilestoneStatus, number>;

  for (const page of pages) {
    const status = normalizeStatus(page.data.status as string | undefined);
    if (status) counts[status] += 1;
  }

  return counts;
}

export function getPhaseStats(slug: PhaseSlug) {
  const milestones = getRoadmapPages().filter(
    (page) =>
      page.slugs[0] === slug && page.slugs.includes("milestones"),
  );

  const counts = countMilestoneStatuses(milestones);
  const total = milestones.length;
  const completed = counts.completed;

  return { milestones, counts, total, completed };
}

export function getOverallRoadmapStats() {
  const milestones = getMilestonePages();
  const counts = countMilestoneStatuses(milestones);
  const total = milestones.length;
  const completed = counts.completed;
  const progressPct = total > 0 ? Math.round((completed / total) * 100) : 0;

  return { counts, total, completed, progressPct };
}

function deriveStatusFromStats(
  stats: ReturnType<typeof getPhaseStats>,
  phaseStatus: MilestoneStatus | undefined,
): MilestoneStatus | undefined {
  if (phaseStatus || stats.total === 0) return phaseStatus;
  if (stats.completed === stats.total) return "completed";
  if (stats.counts["in-progress"] > 0) return "in-progress";
  return "planned";
}

function applyPhaseStatusDefaults(
  slug: PhaseSlug,
  status: MilestoneStatus | undefined,
): MilestoneStatus | undefined {
  if (slug === "phase-0-foundation" || slug === "phase-1-core-platform") {
    return "completed";
  }
  if (slug === "phase-1-5-docs-site" && !status) return "in-progress";
  if (slug === "phase-2-single-provider" && !status) return "planned";
  return status;
}

function resolvePhaseStatus(
  slug: PhaseSlug,
  stats: ReturnType<typeof getPhaseStats>,
  phaseStatus: MilestoneStatus | undefined,
): MilestoneStatus | undefined {
  const derived = deriveStatusFromStats(stats, phaseStatus);
  return applyPhaseStatusDefaults(slug, derived);
}

function resolvePhaseDescription(index: ReturnType<typeof getPhaseIndexPage>) {
  const rawDesc = index?.data.description as string | undefined;
  if (rawDesc && !rawDesc.includes("**")) return rawDesc;

  const summary = index?.data.summary as string | undefined;
  if (summary?.includes("**")) return undefined;
  return summary;
}

export function getPhaseCards() {
  return PHASE_SLUGS.map((slug) => {
    const index = getPhaseIndexPage(slug);
    const stats = getPhaseStats(slug);
    const phaseStatus = normalizeStatus(index?.data.status as string | undefined);

    const milestonesPending =
      stats.total === 0 &&
      ["phase-3-memory-engine", "phase-4-multi-provider", "phase-5-production-hardening"].includes(
        slug,
      );

    return {
      slug,
      title: index?.data.title ?? slug,
      description: resolvePhaseDescription(index),
      subtitle: index?.data.estimatedEffort as string | undefined,
      status: resolvePhaseStatus(slug, stats, phaseStatus),
      completed: stats.completed,
      total: stats.total,
      milestonesPending,
    };
  });
}

export function getRecentCompletedMilestones(limit = 5) {
  return getMilestonePages()
    .filter((page) => normalizeStatus(page.data.status as string | undefined) === "completed")
    .sort((a, b) => {
      const aDate = (a.data.completedDate as string | undefined) ?? "";
      const bDate = (b.data.completedDate as string | undefined) ?? "";
      return bDate.localeCompare(aDate);
    })
    .slice(0, limit)
    .map((page) => ({
      url: page.url,
      title: page.data.title,
      milestoneId: page.data.milestoneId as string | undefined,
    }));
}
