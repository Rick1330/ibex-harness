import { DocsLayout } from "fumadocs-ui/layouts/docs";
import type { ReactNode } from "react";

import { baseOptions, docsLayoutOptions } from "@/lib/layout.config";
import { source } from "@/lib/source";

/** Computed once at module load — avoids re-building the tree each request. */
const pageTree = source.getPageTree();

export const dynamic = "force-static";

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <DocsLayout
      tree={pageTree}
      {...baseOptions()}
      {...docsLayoutOptions()}
    >
      <div className="docs-page-enter">{children}</div>
    </DocsLayout>
  );
}
