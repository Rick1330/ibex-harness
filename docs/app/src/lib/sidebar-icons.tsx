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

export type DocsContentPath = string & { readonly __brand: "DocsContentPath" };
export type RoadmapContentPath = string & { readonly __brand: "RoadmapContentPath" };

function toDocsPath(path: string): DocsContentPath {
  return path as DocsContentPath;
}

function toRoadmapPath(path: string): RoadmapContentPath {
  return path as RoadmapContentPath;
}

export function contentPathFromUrl(
  url: string,
  baseUrl: ContentBaseUrl = "/docs",
): DocsContentPath | RoadmapContentPath {
  const prefix = baseUrl === "/docs" ? /^\/docs\/?/ : /^\/roadmap\/?/;
  const stripped = url.replace(prefix, "").replace(/\/$/, "");
  return baseUrl === "/docs" ? toDocsPath(stripped) : toRoadmapPath(stripped);
}

/** @deprecated Use contentPathFromUrl(url, "/docs") */
export function docPathFromUrl(url: string): DocsContentPath {
  const prefix = /^\/docs\/?/;
  return toDocsPath(url.replace(prefix, "").replace(/\/$/, ""));
}

type NavIconResolver = {
  baseUrl: ContentBaseUrl;
  fallback: LucideIcon;
  lookup: (path: string) => LucideIcon | undefined;
};

const NAV_ICON_RESOLVERS: NavIconResolver[] = [
  {
    baseUrl: "/roadmap",
    fallback: FileText,
    lookup: (path) => lookupRoadmapPathIcon(path),
  },
  {
    baseUrl: "/docs",
    fallback: FileCode,
    lookup: (path) => lookupDocsPathIcon(path),
  },
];

function resolveNamedOrPath(
  iconName: string | undefined,
  url: string | undefined,
  resolver: NavIconResolver,
): LucideIcon {
  const named = iconName ? iconFromLucideName(iconName) : undefined;
  if (named) return named;
  if (!url) return resolver.fallback;

  const path = contentPathFromUrl(url, resolver.baseUrl);
  return resolver.lookup(path) ?? resolver.fallback;
}

export function resolveRoadmapNavIcon(
  iconName?: string,
  url?: string,
): LucideIcon | undefined {
  return resolveNamedOrPath(iconName, url, NAV_ICON_RESOLVERS[0]);
}

export function resolveNavIcon(
  iconName?: string,
  url?: string,
): LucideIcon | undefined {
  if (url?.startsWith("/roadmap")) {
    return resolveRoadmapNavIcon(iconName, url);
  }
  return resolveNamedOrPath(iconName, url, NAV_ICON_RESOLVERS[1]);
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

const ROADMAP_SECTION_ICON_LOOKUP: Record<string, LucideIcon> = {
  ...ROADMAP_PHASE_ICONS,
  ...ROADMAP_SECTION_ICONS,
};

export function getSectionIconForSlug(
  sectionSlug: string,
  baseUrl: ContentBaseUrl = "/docs",
): LucideIcon {
  if (baseUrl === "/roadmap") {
    return ROADMAP_SECTION_ICON_LOOKUP[sectionSlug] ?? FileText;
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
