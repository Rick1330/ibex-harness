"use client";

import type { PageTree } from "fumadocs-core/server";
import { SidebarItem } from "fumadocs-ui/layouts/docs/sidebar";
import { usePathname } from "next/navigation";

import { docsSidebarItemClassName } from "@/components/layout/docs-sidebar";
import { resolveLeafNavIcon } from "@/lib/sidebar-page-icon";
import { baseUrlFromPathname, toNavUrl } from "@/lib/sidebar-icons";

type BenchmarkSidebarItemProps = Readonly<{
  item: PageTree.Item;
}>;

export function BenchmarkSidebarItem({ item }: BenchmarkSidebarItemProps) {
  const pathname = usePathname();
  const baseUrl = baseUrlFromPathname(toNavUrl(pathname));

  return (
    <SidebarItem
      className={docsSidebarItemClassName()}
      external={item.external}
      href={item.url}
      icon={resolveLeafNavIcon(item.url, baseUrl)}
    >
      <span className="sidebar-nav-item-label min-w-0 flex-1">{item.name}</span>
    </SidebarItem>
  );
}
