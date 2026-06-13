import type { BaseLayoutProps } from "fumadocs-ui/layouts/shared";
import type { DocsLayoutProps } from "fumadocs-ui/layouts/docs";

import {
  DocsSidebarFolder,
  DocsSidebarItem,
} from "@/components/layout/docs-sidebar";
import { NavSearch } from "@/components/layout/nav-search";
import { Wordmark } from "@/components/wordmark";
import { GITHUB_OWNER, GITHUB_REPO } from "@/lib/github";

export function baseOptions(): BaseLayoutProps {
  return {
    githubUrl: `https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}`,
    nav: {
      title: <Wordmark />,
    },
  };
}

export function docsLayoutOptions(): Pick<DocsLayoutProps, "sidebar"> {
  return {
    sidebar: {
      defaultOpenLevel: 1,
      collapsible: true,
      hideSearch: true,
      banner: <NavSearch className="max-md:hidden" />,
      components: {
        Item: DocsSidebarItem,
        Folder: DocsSidebarFolder,
      },
    },
  };
}
