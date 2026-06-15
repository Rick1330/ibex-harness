import { type LucideIcon } from "lucide-react";
import { createElement, type ReactElement } from "react";

import { cn } from "@/lib/cn";

export type {
  ContentBaseUrl,
  DocsContentPath,
  NavIconQuery,
  RoadmapContentPath,
} from "@/lib/sidebar-icon-resolvers";

export {
  baseUrlFromPathname,
  contentPathFromUrl,
  createNavIconQuery,
  docPathFromUrl,
  folderSectionSlugFromUrl,
  getNavIconForUrl,
  getRoadmapIconForUrl,
  getSectionIconForSlug,
  resolveNavIcon,
  resolveRoadmapNavIcon,
} from "@/lib/sidebar-icon-resolvers";

import {
  createNavIconQuery,
  resolveNavIcon,
  resolveRoadmapNavIcon,
  type NavIconName,
  type NavUrl,
  type SectionSlug,
} from "@/lib/sidebar-icon-resolvers";

function toNavUrl(url: string): NavUrl {
  return url as NavUrl;
}

function toNavIconName(name: string): NavIconName {
  return name as NavIconName;
}

function toSectionSlug(slug: string): SectionSlug {
  return slug as SectionSlug;
}

export { toNavUrl, toNavIconName, toSectionSlug };

type SidebarIconProps = Readonly<{
  icon: LucideIcon;
  className?: string;
}>;

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
  const Icon = resolveNavIcon(
    createNavIconQuery(
      iconName ? toNavIconName(iconName) : undefined,
      url ? toNavUrl(url) : undefined,
    ),
  );
  if (!Icon) return undefined;
  return createElement(SidebarIcon, { icon: Icon });
}

export function roadmapNavIconElement(
  iconName?: string,
  url?: string,
): ReactElement | undefined {
  const Icon = resolveRoadmapNavIcon(
    createNavIconQuery(
      iconName ? toNavIconName(iconName) : undefined,
      url ? toNavUrl(url) : undefined,
    ),
  );
  if (!Icon) return undefined;
  return createElement(SidebarIcon, { icon: Icon });
}
