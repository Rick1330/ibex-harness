import { Circle, FileCode, FileText, type LucideIcon } from "lucide-react";

import {
  ROADMAP_PHASE_ICONS,
  ROADMAP_SECTION_ICONS,
  ROADMAP_PAGE_ICONS,
  SECTION_ICONS,
  SLUG_ICONS,
  PAGE_ICONS,
  LUCIDE_BY_NAME,
} from "@/lib/sidebar-icon-maps";

export type ContentBaseUrl = "/docs" | "/roadmap";

export type DocsContentPath = string & { readonly __brand: "DocsContentPath" };
export type RoadmapContentPath = string & { readonly __brand: "RoadmapContentPath" };
export type NavIconName = string & { readonly __brand: "NavIconName" };
export type NavUrl = string & { readonly __brand: "NavUrl" };
export type SectionSlug = string & { readonly __brand: "SectionSlug" };

export type NavIconQuery = {
  iconName?: NavIconName;
  url?: NavUrl;
};

type ParsedContentPath = {
  value: string;
  segments: readonly string[];
  leaf: string;
};

type NavIconResolver = {
  baseUrl: ContentBaseUrl;
  fallback: LucideIcon;
  lookup: (path: DocsContentPath | RoadmapContentPath) => LucideIcon | undefined;
};

const URL_PREFIX: Record<ContentBaseUrl, RegExp> = {
  "/docs": /^\/docs\/?/,
  "/roadmap": /^\/roadmap\/?/,
};

const ROADMAP_SECTION_ICON_LOOKUP: Record<string, LucideIcon> = {
  ...ROADMAP_PHASE_ICONS,
  ...ROADMAP_SECTION_ICONS,
};

function toDocsPath(path: string): DocsContentPath {
  return path as DocsContentPath;
}

function toRoadmapPath(path: string): RoadmapContentPath {
  return path as RoadmapContentPath;
}

function toNavUrl(url: string): NavUrl {
  return url as NavUrl;
}

function toNavIconName(name: string): NavIconName {
  return name as NavIconName;
}

function toSectionSlug(slug: string): SectionSlug {
  return slug as SectionSlug;
}

function parseContentPath(path: DocsContentPath | RoadmapContentPath): ParsedContentPath {
  const value = path as string;
  const segments = value.split("/");
  return { value, segments, leaf: segments.at(-1) ?? value };
}

function firstLookupMatch(
  parsed: ParsedContentPath,
  steps: Array<(parsed: ParsedContentPath) => LucideIcon | undefined>,
): LucideIcon | undefined {
  for (const step of steps) {
    const icon = step(parsed);
    if (icon) return icon;
  }
  return undefined;
}

function roadmapPageIcon(parsed: ParsedContentPath): LucideIcon | undefined {
  return ROADMAP_PAGE_ICONS[parsed.value];
}

function roadmapPhaseRootIcon(parsed: ParsedContentPath): LucideIcon | undefined {
  const topLevel = parsed.segments[0];
  if (!topLevel || parsed.segments.length !== 1) return undefined;
  return ROADMAP_PHASE_ICONS[topLevel];
}

function roadmapSectionIcon(parsed: ParsedContentPath): LucideIcon | undefined {
  const section = parsed.segments.find((part) => ROADMAP_SECTION_ICONS[part]);
  return section ? ROADMAP_SECTION_ICONS[section] : undefined;
}

function roadmapMilestoneIcon(parsed: ParsedContentPath): LucideIcon | undefined {
  if (!parsed.value.includes("/milestones/")) return undefined;
  if (!parsed.leaf.startsWith("d") && !/^\d/.test(parsed.leaf)) return undefined;
  return Circle;
}

function roadmapSlugIcon(parsed: ParsedContentPath): LucideIcon | undefined {
  return SLUG_ICONS[parsed.leaf];
}

function roadmapPhaseFallback(parsed: ParsedContentPath): LucideIcon | undefined {
  const topLevel = parsed.segments[0];
  return topLevel ? ROADMAP_PHASE_ICONS[topLevel] : undefined;
}

const ROADMAP_ICON_STEPS = [
  roadmapPageIcon,
  roadmapPhaseRootIcon,
  roadmapSectionIcon,
  roadmapMilestoneIcon,
  roadmapSlugIcon,
  roadmapPhaseFallback,
];

function docsPageIcon(parsed: ParsedContentPath): LucideIcon | undefined {
  return PAGE_ICONS[parsed.value];
}

function docsTopLevelSectionIcon(parsed: ParsedContentPath): LucideIcon | undefined {
  const section = parsed.segments[0];
  if (!section || parsed.value.includes("/")) return undefined;
  return SECTION_ICONS[section];
}

function docsSlugIcon(parsed: ParsedContentPath): LucideIcon | undefined {
  return SLUG_ICONS[parsed.leaf];
}

function docsSectionFallback(parsed: ParsedContentPath): LucideIcon | undefined {
  const section = parsed.segments[0];
  return section ? SECTION_ICONS[section] : undefined;
}

const DOCS_ICON_STEPS = [
  docsPageIcon,
  docsTopLevelSectionIcon,
  docsSlugIcon,
  docsSectionFallback,
];

export function lookupRoadmapPathIcon(path: RoadmapContentPath): LucideIcon | undefined {
  return firstLookupMatch(parseContentPath(path), ROADMAP_ICON_STEPS);
}

export function lookupDocsPathIcon(path: DocsContentPath): LucideIcon | undefined {
  return firstLookupMatch(parseContentPath(path), DOCS_ICON_STEPS);
}

const NAV_ICON_RESOLVERS: Record<ContentBaseUrl, NavIconResolver> = {
  "/roadmap": {
    baseUrl: "/roadmap",
    fallback: FileText,
    lookup: (path) => lookupRoadmapPathIcon(path as RoadmapContentPath),
  },
  "/docs": {
    baseUrl: "/docs",
    fallback: FileCode,
    lookup: (path) => lookupDocsPathIcon(path as DocsContentPath),
  },
};

export function contentPathFromUrl(
  url: NavUrl | string,
  baseUrl: ContentBaseUrl = "/docs",
): DocsContentPath | RoadmapContentPath {
  const stripped = (url as string).replace(URL_PREFIX[baseUrl], "").replace(/\/$/, "");
  return baseUrl === "/docs" ? toDocsPath(stripped) : toRoadmapPath(stripped);
}

/** @deprecated Use contentPathFromUrl(url, "/docs") */
export function docPathFromUrl(url: string): DocsContentPath {
  const stripped = url.replace(URL_PREFIX["/docs"], "").replace(/\/$/, "");
  return toDocsPath(stripped);
}

export function baseUrlFromPathname(pathname: string): ContentBaseUrl {
  return pathname.startsWith("/roadmap") ? "/roadmap" : "/docs";
}

export function folderSectionSlugFromUrl(url: string): SectionSlug {
  const baseUrl: ContentBaseUrl = url.startsWith("/roadmap") ? "/roadmap" : "/docs";
  const section = contentPathFromUrl(toNavUrl(url), baseUrl).split("/")[0] || "section";
  return toSectionSlug(section);
}

export function iconFromLucideName(name: NavIconName | string): LucideIcon | undefined {
  const trimmed = (name as string).trim();
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

function resolveNamedOrPath(query: NavIconQuery, resolver: NavIconResolver): LucideIcon {
  const named = query.iconName ? iconFromLucideName(query.iconName) : undefined;
  if (named) return named;
  if (!query.url) return resolver.fallback;

  const path = contentPathFromUrl(query.url, resolver.baseUrl);
  return resolver.lookup(path) ?? resolver.fallback;
}

export function resolveRoadmapNavIcon(query: NavIconQuery): LucideIcon | undefined {
  return resolveNamedOrPath(query, NAV_ICON_RESOLVERS["/roadmap"]);
}

export function resolveNavIcon(query: NavIconQuery): LucideIcon | undefined {
  if (query.url?.startsWith("/roadmap")) {
    return resolveRoadmapNavIcon(query);
  }
  return resolveNamedOrPath(query, NAV_ICON_RESOLVERS["/docs"]);
}

export function getNavIconForUrl(url: string): LucideIcon {
  return resolveNavIcon({ url: toNavUrl(url) }) ?? FileCode;
}

export function getRoadmapIconForUrl(url: string): LucideIcon {
  return resolveRoadmapNavIcon({ url: toNavUrl(url) }) ?? FileText;
}

export function getSectionIconForSlug(
  sectionSlug: SectionSlug | string,
  baseUrl: ContentBaseUrl = "/docs",
): LucideIcon {
  const slug = toSectionSlug(sectionSlug as string);
  if (baseUrl === "/roadmap") {
    return ROADMAP_SECTION_ICON_LOOKUP[slug as string] ?? FileText;
  }

  return resolveNavIcon({ url: toNavUrl(`/docs/${slug as string}`) }) ?? FileCode;
}

export function createNavIconQuery(iconName?: string, url?: string): NavIconQuery {
  return {
    iconName: iconName ? toNavIconName(iconName) : undefined,
    url: url ? toNavUrl(url) : undefined,
  };
}
