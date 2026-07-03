import { DocsLayout } from "fumadocs-ui/layouts/docs";
import type { ReactNode } from "react";

import {
  benchmarkBaseOptions,
  benchmarkLayoutOptions,
} from "@/lib/benchmark-layout.config";
import { benchmarkPageTree } from "@/lib/benchmark-page-tree";

type BenchmarksLayoutProps = Readonly<{
  children: ReactNode;
}>;

export default function BenchmarksLayout({ children }: BenchmarksLayoutProps) {
  const options = benchmarkBaseOptions();

  return (
    <DocsLayout
      tree={benchmarkPageTree}
      containerProps={{ className: "benchmark-docs-layout" }}
      {...options}
      {...benchmarkLayoutOptions()}
    >
      {children}
    </DocsLayout>
  );
}
