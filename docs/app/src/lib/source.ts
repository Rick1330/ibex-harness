import { blog, docs, roadmap, releases } from "../../.source";
import { createMDXSource } from "fumadocs-mdx";
import { loader } from "fumadocs-core/source";

import {
  contentPathFromUrl,
  navIconElement,
  roadmapNavIconElement,
  toNavUrl,
} from "@/lib/sidebar-icons";

export const source = loader({
  baseUrl: "/docs",
  source: docs.toFumadocsSource(),
  icon: (iconName) => navIconElement(iconName),
  pageTree: {
    attachFile: (node) => ({
      ...node,
      icon: node.icon ?? navIconElement(undefined, node.url),
    }),
    attachFolder: (node) => {
      const path = node.index?.url
        ? contentPathFromUrl(toNavUrl(node.index.url), "/docs").split("/")[0]
        : undefined;

      return {
        ...node,
        icon:
          node.icon ??
          navIconElement(undefined, path ? `/docs/${path}` : node.index?.url),
      };
    },
  },
});

export const blogSource = loader({
  baseUrl: "/blog",
  source: createMDXSource(blog),
});

export const releasesSource = loader({
  baseUrl: "/releases",
  source: createMDXSource(releases),
});

export const roadmapSource = loader({
  baseUrl: "/roadmap",
  source: roadmap.toFumadocsSource(),
  icon: (iconName) => roadmapNavIconElement(iconName),
  pageTree: {
    attachFile: (node) => ({
      ...node,
      icon: node.icon ?? roadmapNavIconElement(undefined, node.url),
    }),
    attachFolder: (node) => {
      const path = node.index?.url
        ? contentPathFromUrl(toNavUrl(node.index.url), "/roadmap")
        : undefined;
      const section = path?.split("/").pop() ?? path?.split("/")[0];

      return {
        ...node,
        icon:
          node.icon ??
          roadmapNavIconElement(
            undefined,
            section ? `/roadmap/${section}` : node.index?.url,
          ),
      };
    },
  },
});
