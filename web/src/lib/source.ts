import { blog, docs, roadmap } from "../../.source";
import { createMDXSource } from "fumadocs-mdx";
import { loader } from "fumadocs-core/source";

import {
  navIconElement,
  roadmapNavIconElement,
} from "@/lib/sidebar-icons";

export const source = loader({
  baseUrl: "/docs",
  source: docs.toFumadocsSource(),
  icon: (iconName) => navIconElement(iconName),
});

export const blogSource = loader({
  baseUrl: "/blog",
  source: createMDXSource(blog),
});

export const roadmapSource = loader({
  baseUrl: "/roadmap",
  source: roadmap.toFumadocsSource(),
  icon: (iconName) => roadmapNavIconElement(iconName),
});
