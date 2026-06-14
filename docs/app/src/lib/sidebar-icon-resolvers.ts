import { Circle, type LucideIcon } from "lucide-react";

import {
  LUCIDE_BY_NAME,
  PAGE_ICONS,
  ROADMAP_PAGE_ICONS,
  ROADMAP_PHASE_ICONS,
  ROADMAP_SECTION_ICONS,
  SECTION_ICONS,
  SLUG_ICONS,
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

function roadmapMilestoneIcon(path: string): LucideIcon | undefined {
  if (!path.includes("/milestones/")) return undefined;
  const slug = path.split("/").pop() ?? "";
  if (slug.startsWith("d") || /^\d/.test(slug)) {
    return Circle;
  }
  return undefined;
}

function roadmapSectionIcon(segments: string[]): LucideIcon | undefined {
  const section = segments.find((part) => ROADMAP_SECTION_ICONS[part]);
  return section ? ROADMAP_SECTION_ICONS[section] : undefined;
}

export function lookupRoadmapPathIcon(path: string): LucideIcon | undefined {
  if (ROADMAP_PAGE_ICONS[path]) return ROADMAP_PAGE_ICONS[path];

  const segments = path.split("/");
  const topLevel = segments[0];

  if (topLevel && ROADMAP_PHASE_ICONS[topLevel] && segments.length === 1) {
    return ROADMAP_PHASE_ICONS[topLevel];
  }

  const sectionIcon = roadmapSectionIcon(segments);
  if (sectionIcon) return sectionIcon;

  const milestoneIcon = roadmapMilestoneIcon(path);
  if (milestoneIcon) return milestoneIcon;

  const leaf = segments.at(-1) ?? path;
  if (SLUG_ICONS[leaf]) return SLUG_ICONS[leaf];
  if (topLevel && ROADMAP_PHASE_ICONS[topLevel]) {
    return ROADMAP_PHASE_ICONS[topLevel];
  }

  return undefined;
}

export function lookupDocsPathIcon(path: string): LucideIcon | undefined {
  if (PAGE_ICONS[path]) return PAGE_ICONS[path];

  const section = path.split("/")[0];
  if (section && SECTION_ICONS[section] && !path.includes("/")) {
    return SECTION_ICONS[section];
  }

  const leaf = path.split("/").pop() ?? path;
  if (SLUG_ICONS[leaf]) return SLUG_ICONS[leaf];
  if (section && SECTION_ICONS[section]) return SECTION_ICONS[section];

  return undefined;
}
