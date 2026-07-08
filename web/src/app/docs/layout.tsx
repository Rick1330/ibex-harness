import { DocsLayout } from "fumadocs-ui/layouts/docs";
import type { ReactNode } from "react";

import { baseOptions, docsLayoutOptions } from "@/lib/layout.config";
import { source } from "@/lib/source";

/** Computed once at module load — avoids re-building the tree each request. */
const pageTree = source.getPageTree();

export const dynamic = "force-static";

type DocsLayoutWrapperProps = Readonly<{
  children: ReactNode;
}>;

export default function Layout({ children }: DocsLayoutWrapperProps) {
  const options = baseOptions();

  return (
    <DocsLayout
      tree={pageTree}
      containerProps={{ className: "docs-content-layout" }}
      {...options}
      {...docsLayoutOptions()}
    >
      {children}
    </DocsLayout>
  );
}
