import { type LucideIcon } from "lucide-react";
import { createElement, type ReactElement } from "react";

import { cn } from "@/lib/cn";
import {
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
  type ContentBaseUrl,
  type DocsContentPath,
  type NavIconQuery,
  type RoadmapContentPath,
} from "@/lib/sidebar-icon-resolvers";

export type {
  ContentBaseUrl,
  DocsContentPath,
  NavIconQuery,
  RoadmapContentPath,
};

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
};

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
  const Icon = resolveNavIcon(createNavIconQuery(iconName, url));
  if (!Icon) return undefined;
  return createElement(SidebarIcon, { icon: Icon });
}

export function roadmapNavIconElement(
  iconName?: string,
  url?: string,
): ReactElement | undefined {
  const Icon = resolveRoadmapNavIcon(createNavIconQuery(iconName, url));
  if (!Icon) return undefined;
  return createElement(SidebarIcon, { icon: Icon });
}
