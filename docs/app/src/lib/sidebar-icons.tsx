import { FileCode, FileText, type LucideIcon } from "lucide-react";
import { createElement, type ReactElement } from "react";

import { cn } from "@/lib/cn";
import {
  ROADMAP_PHASE_ICONS,
  ROADMAP_SECTION_ICONS,
} from "@/lib/sidebar-icon-maps";
import {
  iconFromLucideName,
  lookupDocsPathIcon,
  lookupRoadmapPathIcon,
} from "@/lib/sidebar-icon-resolvers";

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

export function resolveRoadmapNavIcon(
  iconName?: string,
  url?: string,
): LucideIcon | undefined {
  const named = iconName ? iconFromLucideName(iconName) : undefined;
  if (named) return named;
  if (!url) return FileText;

  const path = contentPathFromUrl(url, "/roadmap");
  return lookupRoadmapPathIcon(path) ?? FileText;
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
  return lookupDocsPathIcon(path) ?? FileCode;
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
