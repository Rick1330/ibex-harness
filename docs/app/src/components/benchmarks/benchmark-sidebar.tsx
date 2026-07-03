"use client";

import type { PageTree } from "fumadocs-core/server";
import { SidebarItem } from "fumadocs-ui/layouts/docs/sidebar";
import { createElement } from "react";

import { docsSidebarItemClassName } from "@/components/layout/docs-sidebar";
import { BENCHMARK_PAGE_ICONS } from "@/lib/sidebar-icon-maps";
import { SidebarIcon } from "@/lib/sidebar-icons";

type BenchmarkSidebarItemProps = Readonly<{
  item: PageTree.Item;
}>;

export function BenchmarkSidebarItem({ item }: BenchmarkSidebarItemProps) {
  const Icon = BENCHMARK_PAGE_ICONS[item.url] ?? BENCHMARK_PAGE_ICONS["/benchmarks"];

  return (
    <SidebarItem
      className={docsSidebarItemClassName()}
      external={item.external}
      href={item.url}
      icon={Icon ? createElement(SidebarIcon, { icon: Icon }) : undefined}
    >
      {item.name}
    </SidebarItem>
  );
}
