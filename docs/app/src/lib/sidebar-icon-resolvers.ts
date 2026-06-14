import { Circle, type LucideIcon } from "lucide-react";

import {
  ROADMAP_PAGE_ICONS,
  ROADMAP_PHASE_ICONS,
  ROADMAP_SECTION_ICONS,
  SECTION_ICONS,
  SLUG_ICONS,
  PAGE_ICONS,
  LUCIDE_BY_NAME,
} from "@/lib/sidebar-icon-maps";

export function iconFromLucideName(name: string): LucideIcon | undefined {
  const trimmed = name.trim();
  if (!trimmed) return undefined;

  if (trimmed in LUCIDE_BY_NAME) {
    return LUCIDE_BY_NAME[trimmed];
  }

  const pascal = trimmed
    .split(/[-_\s]+/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");

  return LUCIDE_BY_NAME[pascal];
}

function splitPath(path: string) {
  return path.split("/");
}

function roadmapMilestoneIcon(path: string): LucideIcon | undefined {
  if (!path.includes("/milestones/")) return undefined;
  const slug = path.split("/").pop() ?? "";
  if (!slug.startsWith("d") && !/^\d/.test(slug)) return undefined;
  return Circle;
}

function roadmapSectionIcon(segments: string[]): LucideIcon | undefined {
  const section = segments.find((part) => ROADMAP_SECTION_ICONS[part]);
  return section ? ROADMAP_SECTION_ICONS[section] : undefined;
}

function roadmapPhaseRootIcon(segments: string[]): LucideIcon | undefined {
  const topLevel = segments[0];
  if (!topLevel || segments.length !== 1) return undefined;
  return ROADMAP_PHASE_ICONS[topLevel];
}

function roadmapPhaseFallback(segments: string[]): LucideIcon | undefined {
  const topLevel = segments[0];
  return topLevel ? ROADMAP_PHASE_ICONS[topLevel] : undefined;
}

export function lookupRoadmapPathIcon(path: string): LucideIcon | undefined {
  const segments = splitPath(path);
  const leaf = segments.at(-1) ?? path;

  return (
    ROADMAP_PAGE_ICONS[path] ??
    roadmapPhaseRootIcon(segments) ??
    roadmapSectionIcon(segments) ??
    roadmapMilestoneIcon(path) ??
    SLUG_ICONS[leaf] ??
    roadmapPhaseFallback(segments)
  );
}

export function lookupDocsPathIcon(path: string): LucideIcon | undefined {
  const section = splitPath(path)[0];
  const leaf = path.split("/").pop() ?? path;

  return (
    PAGE_ICONS[path] ??
    (section && SECTION_ICONS[section] && !path.includes("/") ? SECTION_ICONS[section] : undefined) ??
    SLUG_ICONS[leaf] ??
    (section ? SECTION_ICONS[section] : undefined)
  );
}
