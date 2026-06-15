import type { ReactNode } from "react";

import {
  navIconElement,
  roadmapNavIconElement,
  toNavUrl,
  type ContentBaseUrl,
} from "@/lib/sidebar-icons";

/** Resolve sidebar/footer icons from URL — never reuse stale tree-attached icons. */
export function resolveLeafNavIcon(
  url: string,
  baseUrl: ContentBaseUrl,
): ReactNode {
  const iconResolver =
    baseUrl === "/roadmap" ? roadmapNavIconElement : navIconElement;

  return iconResolver(undefined, toNavUrl(url));
}
