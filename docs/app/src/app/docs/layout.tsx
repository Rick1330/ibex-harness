import { DocsLayout } from "fumadocs-ui/layouts/docs";
import type { ReactNode } from "react";

import { baseOptions, docsLayoutOptions } from "@/lib/layout.config";
import { source } from "@/lib/source";

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <DocsLayout
      tree={source.getPageTree()}
      {...baseOptions()}
      {...docsLayoutOptions()}
    >
      {children}
    </DocsLayout>
  );
}
