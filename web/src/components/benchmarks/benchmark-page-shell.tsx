import { DocsPage } from "fumadocs-ui/page";
import type { ReactNode } from "react";

import { BenchmarkFooter } from "@/components/benchmarks/benchmark-footer";
import { BenchmarkPageHeader } from "@/components/benchmarks/benchmark-page-header";
import { DocsBreadcrumb } from "@/components/layout/breadcrumb";
import { DocsFooterNav } from "@/components/layout/docs-footer-nav";
import { benchmarkPageTree } from "@/lib/benchmark-page-tree";

type BenchmarkPageShellProps = Readonly<{
  title: string;
  subtitle: string;
  children: ReactNode;
}>;

export function BenchmarkPageShell({ title, subtitle, children }: BenchmarkPageShellProps) {
  return (
    <DocsPage
      full
      breadcrumb={{ component: <DocsBreadcrumb tree={benchmarkPageTree} /> }}
      footer={{ component: <DocsFooterNav /> }}
      tableOfContent={{ enabled: false }}
      tableOfContentPopover={{ enabled: false }}
    >
      <BenchmarkPageHeader title={title} subtitle={subtitle} />
      <div className="benchmark-section">{children}</div>
      <BenchmarkFooter />
    </DocsPage>
  );
}
