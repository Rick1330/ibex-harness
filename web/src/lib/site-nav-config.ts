import type { MobileNavData } from "@/lib/mobile-nav-data";
import type { ContentBaseUrl } from "@/lib/sidebar-icon-resolvers";

export const LANDING_SITE_URL = "/";

export const LANDING_NAV_LINK = {
  text: "Home",
  href: LANDING_SITE_URL,
  external: false,
} as const;

export const NAV_LINKS = [
  {
    text: "Docs",
    href: "/docs/getting-started/introduction",
    match: "/docs",
  },
  {
    text: "Benchmarks",
    href: "/benchmarks",
    match: "/benchmarks",
  },
  {
    text: "Blog",
    href: "/blog",
    match: "/blog",
  },
  {
    text: "Changelog",
    href: "/releases",
    match: "/releases",
  },
  {
    text: "Roadmap",
    href: "/roadmap",
    match: "/roadmap",
  },
] as const;

export type MobileSectionIconId = "docs" | "benchmarks" | "blog" | "releases" | "roadmap";

export function isLinkActive(pathname: string, match: string) {
  return pathname.startsWith(match);
}

type MobileSectionKind = "tree" | "list";

type MobileSectionMeta = Readonly<{
  kind: MobileSectionKind;
  dataKey: keyof MobileNavData;
  baseUrl?: ContentBaseUrl;
  hub?: Readonly<{ href: string; label: string }>;
  description: string;
  iconId: MobileSectionIconId;
}>;

const MOBILE_SECTION_META: Record<
  (typeof NAV_LINKS)[number]["match"],
  MobileSectionMeta
> = {
  "/docs": {
    kind: "tree",
    dataKey: "docsTree",
    baseUrl: "/docs",
    description: "Reference and guides",
    iconId: "docs",
  },
  "/benchmarks": {
    kind: "list",
    dataKey: "benchmarkPages",
    hub: { href: "/benchmarks", label: "Overview" },
    description: "Proxy performance and regression",
    iconId: "benchmarks",
  },
  "/blog": {
    kind: "list",
    dataKey: "blogPosts",
    hub: { href: "/blog", label: "All posts" },
    description: "Engineering notes",
    iconId: "blog",
  },
  "/releases": {
    kind: "list",
    dataKey: "releasePages",
    hub: { href: "/releases", label: "Changelog" },
    description: "Version changelog",
    iconId: "releases",
  },
  "/roadmap": {
    kind: "tree",
    dataKey: "roadmapTree",
    baseUrl: "/roadmap",
    hub: { href: "/roadmap", label: "Roadmap overview" },
    description: "Phases and milestones",
    iconId: "roadmap",
  },
};

export type MobileNavSectionConfig = Readonly<{
  id: string;
  title: string;
  match: string;
  href: string;
  description: string;
  iconId: MobileSectionIconId;
  kind: MobileSectionKind;
  dataKey: keyof MobileNavData;
  baseUrl?: ContentBaseUrl;
  hub?: Readonly<{ href: string; label: string }>;
}>;

export const MOBILE_NAV_SECTIONS: MobileNavSectionConfig[] = NAV_LINKS.map(
  (link) => {
    const meta = MOBILE_SECTION_META[link.match];
    return {
      id: link.match.slice(1),
      title: link.text,
      match: link.match,
      href: link.href,
      ...meta,
    };
  },
);

export function resolveActiveMobileSection(pathname: string): string | null {
  const section = MOBILE_NAV_SECTIONS.find((entry) =>
    isLinkActive(pathname, entry.match),
  );
  if (!section) return null;
  return section.id;
}

export function getActiveMobileSection(
  pathname: string,
): MobileNavSectionConfig {
  const id = resolveActiveMobileSection(pathname);
  const match = MOBILE_NAV_SECTIONS.find((section) => section.id === id);
  if (match) return match;
  return MOBILE_NAV_SECTIONS[0];
}

/** Absolute marketing URL for JSON-LD and external citations. */
export { SITE_URL as SITE_ABSOLUTE_URL } from "@/lib/site-seo";
