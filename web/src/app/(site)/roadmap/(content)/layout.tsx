import { DocsLayout } from "fumadocs-ui/layouts/docs";
import type { ReactNode } from "react";

import {
  roadmapBaseOptions,
  roadmapLayoutOptions,
} from "@/lib/roadmap-layout.config";
import { roadmapSource } from "@/lib/source";

const pageTree = roadmapSource.getPageTree();

export const dynamic = "force-static";

type RoadmapContentLayoutProps = Readonly<{
  children: ReactNode;
}>;

export default function RoadmapContentLayout({
  children,
}: RoadmapContentLayoutProps) {
  const options = roadmapBaseOptions();

  return (
    <DocsLayout
      tree={pageTree}
      containerProps={{ className: "roadmap-docs-layout" }}
      {...options}
      {...roadmapLayoutOptions()}
    >
      {children}
    </DocsLayout>
  );
}
