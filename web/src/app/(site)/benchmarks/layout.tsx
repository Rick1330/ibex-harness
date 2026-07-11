import { DocsLayout } from "fumadocs-ui/layouts/docs";
import type { ReactNode } from "react";

import { BenchmarkProvider } from "@/components/benchmarks/benchmark-provider";
import {
  benchmarkBaseOptions,
  benchmarkLayoutOptions,
} from "@/lib/benchmark-layout.config";
import { benchmarkPageTree } from "@/lib/benchmark-page-tree";

export const dynamic = "force-static";

type BenchmarksLayoutProps = Readonly<{
  children: ReactNode;
}>;

export default function BenchmarksLayout({ children }: BenchmarksLayoutProps) {
  const options = benchmarkBaseOptions();

  return (
    <BenchmarkProvider>
      <DocsLayout
        tree={benchmarkPageTree}
        containerProps={{ className: "benchmark-docs-layout" }}
        {...options}
        {...benchmarkLayoutOptions()}
      >
        {children}
      </DocsLayout>
    </BenchmarkProvider>
  );
}
