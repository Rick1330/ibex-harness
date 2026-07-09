import { createElement, type ReactNode } from "react";

import {
  navIconElement,
  roadmapNavIconElement,
  getBenchmarkIconForUrl,
  SidebarIcon,
  toNavUrl,
  type ContentBaseUrl,
} from "@/lib/sidebar-icons";

/** Resolve sidebar/footer icons from URL — never reuse stale tree-attached icons. */
export function resolveLeafNavIcon(
  url: string,
  baseUrl: ContentBaseUrl,
): ReactNode {
  if (baseUrl === "/benchmarks") {
    const Icon = getBenchmarkIconForUrl(toNavUrl(url));
    return createElement(SidebarIcon, { icon: Icon });
  }

  const iconResolver =
    baseUrl === "/roadmap" ? roadmapNavIconElement : navIconElement;

  return iconResolver(undefined, toNavUrl(url));
}
