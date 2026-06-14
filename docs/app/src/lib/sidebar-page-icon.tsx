import type { ReactNode } from "react";

import {
  navIconElement,
  roadmapNavIconElement,
  toNavUrl,
  type ContentBaseUrl,
} from "@/lib/sidebar-icons";

export function resolveLeafNavIcon(
  treeIcon: ReactNode | undefined,
  url: string,
  baseUrl: ContentBaseUrl,
): ReactNode {
  if (treeIcon) return treeIcon;

  const iconResolver =
    baseUrl === "/roadmap" ? roadmapNavIconElement : navIconElement;

  return iconResolver(undefined, toNavUrl(url));
}
