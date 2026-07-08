import type { BaseLayoutProps } from "fumadocs-ui/layouts/shared";
import type { DocsLayoutProps } from "fumadocs-ui/layouts/docs";

import { BenchmarkSidebarBanner } from "@/components/benchmarks/benchmark-sidebar-banner";
import { BenchmarkSidebarItem } from "@/components/benchmarks/benchmark-sidebar";
import { DocsSidebarFolder } from "@/components/layout/docs-sidebar";

export function benchmarkBaseOptions(): BaseLayoutProps {
  return {
    disableThemeSwitch: true,
    nav: {
      enabled: false,
    },
  };
}

export function benchmarkLayoutOptions(): Pick<DocsLayoutProps, "sidebar"> {
  return {
    sidebar: {
      defaultOpenLevel: 0,
      collapsible: true,
      hideSearch: true,
      banner: <BenchmarkSidebarBanner />,
      components: {
        Item: BenchmarkSidebarItem,
        Folder: DocsSidebarFolder,
      },
    },
  };
}
