import {
  BookOpen,
  Circle,
  Gauge,
  Map,
  type LucideIcon,
} from "lucide-react";

import {
  ROADMAP_PHASE_ICONS,
  ROADMAP_SECTION_ICONS,
  ROADMAP_PAGE_ICONS,
  BENCHMARK_PAGE_ICONS,
  SECTION_ICONS,
  SLUG_ICONS,
  PAGE_ICONS,
  LUCIDE_BY_NAME,
} from "@/lib/sidebar-icon-maps";

export type ContentBaseUrl = "/docs" | "/roadmap" | "/benchmarks";

export type DocsContentPath = string & { readonly __brand: "DocsContentPath" };
export type RoadmapContentPath = string & { readonly __brand: "RoadmapContentPath" };
export type BenchmarkContentPath = string & { readonly __brand: "BenchmarkContentPath" };
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

type IconLookupStep = (parsed: ParsedContentPath) => LucideIcon | undefined;

const URL_PREFIX: Record<ContentBaseUrl, RegExp> = {
  "/docs": /^\/docs\/?/,
  "/roadmap": /^\/roadmap\/?/,
  "/benchmarks": /^\/benchmarks\/?/,
};

const ROADMAP_SECTION_ICON_LOOKUP: Record<string, LucideIcon> = {
  ...ROADMAP_PHASE_ICONS,
  ...ROADMAP_SECTION_ICONS,
};

function brand<T extends string>(value: string): T {
  return value as T;
}

function parseContentPath(
  path: DocsContentPath | RoadmapContentPath | BenchmarkContentPath,
): ParsedContentPath {
  const value = path as string;
  const segments = value.split("/");
  return { value, segments, leaf: segments.at(-1) ?? value };
}

function firstLookupMatch(
  parsed: ParsedContentPath,
  steps: readonly IconLookupStep[],
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

const ROADMAP_ICON_STEPS: readonly IconLookupStep[] = [
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

const DOCS_ICON_STEPS: readonly IconLookupStep[] = [
  docsPageIcon,
  docsTopLevelSectionIcon,
  docsSlugIcon,
  docsSectionFallback,
];

function sectionIconForPath(
  parsed: ParsedContentPath,
  site: ContentBaseUrl,
): LucideIcon | undefined {
  const section = parsed.segments[0];
  if (!section) return undefined;

  if (site === "/roadmap") {
    return (
      ROADMAP_PAGE_ICONS[parsed.value] ??
      ROADMAP_SECTION_ICONS[section] ??
      ROADMAP_PHASE_ICONS[section]
    );
  }

  return SECTION_ICONS[section];
}

class SiteNavIconService {
  private constructor(
    private readonly site: ContentBaseUrl,
    private readonly defaultIcon: LucideIcon,
    private readonly steps: readonly IconLookupStep[],
  ) {}

  static readonly docs = new SiteNavIconService("/docs", BookOpen, DOCS_ICON_STEPS);
  static readonly roadmap = new SiteNavIconService("/roadmap", Map, ROADMAP_ICON_STEPS);

  resolve(query: NavIconQuery): LucideIcon {
    const named = query.iconName ? iconFromLucideName(query.iconName) : undefined;
    if (named) return named;
    if (!query.url) return this.defaultIcon;

    const path = contentPathFromUrl(query.url, this.site);
    const parsed = parseContentPath(path);
    return (
      firstLookupMatch(parsed, this.steps) ??
      sectionIconForPath(parsed, this.site) ??
      this.defaultIcon
    );
  }
}

export function lookupRoadmapPathIcon(path: RoadmapContentPath): LucideIcon | undefined {
  return firstLookupMatch(parseContentPath(path), ROADMAP_ICON_STEPS);
}

export function lookupDocsPathIcon(path: DocsContentPath): LucideIcon | undefined {
  return firstLookupMatch(parseContentPath(path), DOCS_ICON_STEPS);
}

export function contentPathFromUrl(
  url: NavUrl,
  baseUrl: ContentBaseUrl = "/docs",
): DocsContentPath | RoadmapContentPath | BenchmarkContentPath {
  const stripped = (url as string).replace(URL_PREFIX[baseUrl], "").replace(/\/$/, "");
  if (baseUrl === "/roadmap") {
    return brand<RoadmapContentPath>(stripped);
  }
  if (baseUrl === "/benchmarks") {
    return brand<BenchmarkContentPath>(stripped);
  }
  return brand<DocsContentPath>(stripped);
}

export function createNavIconQuery(
  iconName?: NavIconName,
  url?: NavUrl,
): NavIconQuery {
  return { iconName, url };
}

/** @deprecated Use contentPathFromUrl(url, "/docs") */
export function docPathFromUrl(url: NavUrl): DocsContentPath {
  const stripped = (url as string).replace(URL_PREFIX["/docs"], "").replace(/\/$/, "");
  return brand<DocsContentPath>(stripped);
}

export function baseUrlFromPathname(pathname: NavUrl): ContentBaseUrl {
  const value = pathname as string;
  if (value.startsWith("/roadmap")) return "/roadmap";
  if (value.startsWith("/benchmarks")) return "/benchmarks";
  return "/docs";
}

export function folderSectionSlugFromUrl(url: NavUrl): SectionSlug {
  const baseUrl = baseUrlFromPathname(url);
  const section = contentPathFromUrl(url, baseUrl).split("/")[0] || "section";
  return brand<SectionSlug>(section);
}

export function iconFromLucideName(name: NavIconName): LucideIcon | undefined {
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

export function resolveRoadmapNavIcon(query: NavIconQuery): LucideIcon | undefined {
  return SiteNavIconService.roadmap.resolve(query);
}

export function resolveNavIcon(query: NavIconQuery): LucideIcon | undefined {
  if (query.url?.startsWith("/benchmarks")) {
    return BENCHMARK_PAGE_ICONS[query.url as string] ?? Gauge;
  }
  if (query.url?.startsWith("/roadmap")) {
    return SiteNavIconService.roadmap.resolve(query);
  }
  return SiteNavIconService.docs.resolve(query);
}

export function getBenchmarkIconForUrl(url: NavUrl): LucideIcon {
  return BENCHMARK_PAGE_ICONS[url as string] ?? Gauge;
}

export function getNavIconForUrl(url: NavUrl): LucideIcon {
  const baseUrl = baseUrlFromPathname(url);
  if (baseUrl === "/benchmarks") {
    return getBenchmarkIconForUrl(url);
  }
  return (
    resolveNavIcon(createNavIconQuery(undefined, url)) ??
    SECTION_ICONS[contentPathFromUrl(url, baseUrl).split("/")[0] ?? ""] ??
    BookOpen
  );
}

export function getRoadmapIconForUrl(url: NavUrl): LucideIcon {
  const section = contentPathFromUrl(url, "/roadmap").split("/")[0] ?? "";
  return (
    resolveRoadmapNavIcon(createNavIconQuery(undefined, url)) ??
    ROADMAP_SECTION_ICON_LOOKUP[section] ??
    Map
  );
}

export function getSectionIconForSlug(
  sectionSlug: SectionSlug,
  baseUrl: ContentBaseUrl = "/docs",
): LucideIcon {
  const slug = sectionSlug as string;
  if (baseUrl === "/roadmap") {
    return ROADMAP_SECTION_ICON_LOOKUP[slug] ?? Map;
  }

  return SiteNavIconService.docs.resolve({
    url: brand<NavUrl>(`/docs/${slug}`),
  });
}

