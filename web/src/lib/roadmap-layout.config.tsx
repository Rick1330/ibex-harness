import type { BaseLayoutProps } from "fumadocs-ui/layouts/shared";
import type { DocsLayoutProps } from "fumadocs-ui/layouts/docs";
import Link from "next/link";

import {
  DocsSidebarFolder,
  DocsSidebarItem,
} from "@/components/layout/docs-sidebar";

function RoadmapSidebarBanner() {
  return (
    <div className="sidebar-banner flex flex-col gap-3 border-b border-border px-1 pb-5">
      <p className="px-1 text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
        Roadmap
      </p>
      <Link
        href="/roadmap"
        className="rounded-[4px] px-2 py-1.5 text-sm font-medium text-text-secondary transition-colors hover:bg-panel-raised hover:text-text-primary"
      >
        ← Back to overview
      </Link>
    </div>
  );
}

export function roadmapBaseOptions(): BaseLayoutProps {
  return {
    disableThemeSwitch: true,
    nav: {
      enabled: false,
    },
  };
}

export function roadmapLayoutOptions(): Pick<DocsLayoutProps, "sidebar"> {
  return {
    sidebar: {
      defaultOpenLevel: 1,
      collapsible: true,
      hideSearch: true,
      banner: <RoadmapSidebarBanner />,
      components: {
        Item: DocsSidebarItem,
        Folder: DocsSidebarFolder,
      },
    },
  };
}

export function getRoadmapContentFilePath(relativePath: string): string {
  const normalized = relativePath.replaceAll("\\", "/");
  return `web/content/roadmap/${normalized}`;
}
