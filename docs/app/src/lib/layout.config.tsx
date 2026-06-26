import type { BaseLayoutProps } from "fumadocs-ui/layouts/shared";
import type { DocsLayoutProps } from "fumadocs-ui/layouts/docs";

import {
  DocsSidebarFolder,
  DocsSidebarItem,
} from "@/components/layout/docs-sidebar";
import { NavSearch } from "@/components/layout/nav-search";
import { Wordmark } from "@/components/wordmark";

function SidebarSectionLabel() {
  return (
    <p className="px-1 text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
      Documentation
    </p>
  );
}

export function baseOptions(): BaseLayoutProps {
  return {
    disableThemeSwitch: true,
    nav: {
      enabled: false,
      title: <Wordmark />,
    },
  };
}

export function docsLayoutOptions(): Pick<DocsLayoutProps, "sidebar"> {
  return {
    sidebar: {
      defaultOpenLevel: 0,
      collapsible: true,
      hideSearch: true,
      banner: (
        <div className="sidebar-banner flex flex-col gap-4 border-b border-border px-1 pb-5">
          <SidebarSectionLabel />
          <NavSearch className="max-md:hidden" />
        </div>
      ),
      components: {
        Item: DocsSidebarItem,
        Folder: DocsSidebarFolder,
      },
    },
  };
}
