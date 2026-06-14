import { Circle, FileCode, FileText, type LucideIcon } from "lucide-react";
import { createElement, type ReactElement } from "react";

import { cn } from "@/lib/cn";
import {
  LUCIDE_BY_NAME,
  PAGE_ICONS,
  ROADMAP_PAGE_ICONS,
  ROADMAP_PHASE_ICONS,
  ROADMAP_SECTION_ICONS,
  SECTION_ICONS,
  SLUG_ICONS,
} from "@/lib/sidebar-icon-maps";

export type ContentBaseUrl = "/docs" | "/roadmap";

export function contentPathFromUrl(
  url: string,
  baseUrl: ContentBaseUrl = "/docs",
): string {
  const prefix = baseUrl === "/docs" ? /^\/docs\/?/ : /^\/roadmap\/?/;
  return url.replace(prefix, "").replace(/\/$/, "");
}

/** @deprecated Use contentPathFromUrl(url, "/docs") */
export function docPathFromUrl(url: string): string {
  return contentPathFromUrl(url, "/docs");
}

function iconFromLucideName(name: string): LucideIcon | undefined {
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

function resolveRoadmapMilestoneIcon(path: string): LucideIcon | undefined {
  if (!path.includes("/milestones/")) return undefined;

  const slug = path.split("/").pop() ?? "";
  if (slug.startsWith("d") || /^\d/.test(slug)) {
    return Circle;
  }

  return FileText;
}

export function resolveRoadmapNavIcon(
  iconName?: string,
  url?: string,
): LucideIcon | undefined {
  const named = iconName ? iconFromLucideName(iconName) : undefined;
  if (named) return named;

  if (!url) return FileText;

  const path = contentPathFromUrl(url, "/roadmap");
  if (ROADMAP_PAGE_ICONS[path]) return ROADMAP_PAGE_ICONS[path];

  const segments = path.split("/");
  const topLevel = segments[0];
  if (topLevel && ROADMAP_PHASE_ICONS[topLevel] && segments.length === 1) {
    return ROADMAP_PHASE_ICONS[topLevel];
  }

  const section = segments.find((s) => ROADMAP_SECTION_ICONS[s]);
  if (section) return ROADMAP_SECTION_ICONS[section];

  const milestoneIcon = resolveRoadmapMilestoneIcon(path);
  if (milestoneIcon) return milestoneIcon;

  const leaf = segments.pop() ?? path;
  if (SLUG_ICONS[leaf]) return SLUG_ICONS[leaf];
  if (topLevel && ROADMAP_PHASE_ICONS[topLevel]) {
    return ROADMAP_PHASE_ICONS[topLevel];
  }

  return FileText;
}

export function resolveNavIcon(
  iconName?: string,
  url?: string,
): LucideIcon | undefined {
  if (url?.startsWith("/roadmap")) {
    return resolveRoadmapNavIcon(iconName, url);
  }

  const named = iconName ? iconFromLucideName(iconName) : undefined;
  if (named) return named;

  if (!url) return FileCode;

  const path = contentPathFromUrl(url, "/docs");
  if (PAGE_ICONS[path]) return PAGE_ICONS[path];

  const section = path.split("/")[0];
  if (section && SECTION_ICONS[section] && !path.includes("/")) {
    return SECTION_ICONS[section];
  }

  const leaf = path.split("/").pop() ?? path;
  if (SLUG_ICONS[leaf]) return SLUG_ICONS[leaf];
  if (SECTION_ICONS[section]) return SECTION_ICONS[section];

  return FileCode;
}

type SidebarIconProps = {
  icon: LucideIcon;
  className?: string;
};

export function SidebarIcon({ icon: Icon, className }: SidebarIconProps) {
  return (
    <Icon
      aria-hidden
      className={cn("size-4 shrink-0 text-text-primary", className)}
      strokeWidth={2}
    />
  );
}

export function navIconElement(
  iconName?: string,
  url?: string,
): ReactElement | undefined {
  const Icon = resolveNavIcon(iconName, url);
  if (!Icon) return undefined;
  return createElement(SidebarIcon, { icon: Icon });
}

export function roadmapNavIconElement(
  iconName?: string,
  url?: string,
): ReactElement | undefined {
  const Icon = resolveRoadmapNavIcon(iconName, url);
  if (!Icon) return undefined;
  return createElement(SidebarIcon, { icon: Icon });
}

export function getNavIconForUrl(url: string): LucideIcon {
  return resolveNavIcon(undefined, url) ?? FileCode;
}

export function getRoadmapIconForUrl(url: string): LucideIcon {
  return resolveRoadmapNavIcon(undefined, url) ?? FileText;
}

export function getSectionIconForSlug(
  sectionSlug: string,
  baseUrl: ContentBaseUrl = "/docs",
): LucideIcon {
  if (baseUrl === "/roadmap") {
    return (
      ROADMAP_PHASE_ICONS[sectionSlug] ??
      ROADMAP_SECTION_ICONS[sectionSlug] ??
      FileText
    );
  }

  return resolveNavIcon(undefined, `/docs/${sectionSlug}`) ?? FileCode;
}

export function baseUrlFromPathname(pathname: string): ContentBaseUrl {
  return pathname.startsWith("/roadmap") ? "/roadmap" : "/docs";
}

export function folderSectionSlugFromUrl(url: string): string {
  const baseUrl = url.startsWith("/roadmap") ? "/roadmap" : "/docs";
  return contentPathFromUrl(url, baseUrl).split("/")[0] || "section";
}
