import { DocsLayout } from "fumadocs-ui/layouts/docs";
import type { ReactNode } from "react";

import { MobileDocsNav } from "@/components/layout/mobile-docs-nav";
import { baseOptions, docsLayoutOptions } from "@/lib/layout.config";
import { source } from "@/lib/source";

/** Computed once at module load — avoids re-building the tree each request. */
const pageTree = source.getPageTree();

export const dynamic = "force-static";

export default function Layout({ children }: { children: ReactNode }) {
  const options = baseOptions();

  return (
    <DocsLayout
      tree={pageTree}
      {...options}
      nav={{
        ...options.nav,
        enabled: true,
        component: <MobileDocsNav />,
      }}
      {...docsLayoutOptions()}
    >
      {children}
    </DocsLayout>
  );
}
