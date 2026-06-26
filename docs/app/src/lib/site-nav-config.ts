import type { MobileNavData } from "@/lib/mobile-nav-data";
import type { ContentBaseUrl } from "@/lib/sidebar-icon-resolvers";

export const NAV_LINKS = [
  {
    text: "Docs",
    href: "/docs/getting-started/introduction",
    match: "/docs",
  },
  {
    text: "Blog",
    href: "/blog",
    match: "/blog",
  },
  {
    text: "Releases",
    href: "/releases",
    match: "/releases",
  },
  {
    text: "Roadmap",
    href: "/roadmap",
    match: "/roadmap",
  },
] as const;

export type MobileSectionIconId = "docs" | "blog" | "releases" | "roadmap";

export function isLinkActive(pathname: string, match: string) {
  return match === "/docs"
    ? pathname.startsWith("/docs")
    : pathname.startsWith(match);
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
  return section?.id ?? null;
}

export function getActiveMobileSection(
  pathname: string,
): MobileNavSectionConfig {
  const id = resolveActiveMobileSection(pathname);
  return (
    MOBILE_NAV_SECTIONS.find((section) => section.id === id) ??
    MOBILE_NAV_SECTIONS[0]
  );
}
