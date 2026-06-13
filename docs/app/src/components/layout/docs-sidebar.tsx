"use client";

import type { PageTree } from "fumadocs-core/server";
import {
  SidebarFolder,
  SidebarFolderContent,
  SidebarFolderLink,
  SidebarFolderTrigger,
  SidebarItem,
} from "fumadocs-ui/layouts/docs/sidebar";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

const itemClassName =
  "flex h-8 items-center gap-2 rounded-[4px] px-3 text-sm text-text-secondary transition-none hover:bg-panel-raised hover:text-text-primary data-[active=true]:bg-panel-raised data-[active=true]:font-medium data-[active=true]:text-text-primary [&_svg]:size-4";

function folderContainsPath(
  folder: PageTree.Folder,
  pathname: string,
): boolean {
  if (folder.index?.url === pathname) return true;

  return folder.children.some((child) => {
    if (child.type === "page") return child.url === pathname;
    if (child.type === "folder") return folderContainsPath(child, pathname);
    return false;
  });
}

export function DocsSidebarItem({ item }: { item: PageTree.Item }) {
  return (
    <SidebarItem
      href={item.url}
      external={item.external}
      icon={item.icon}
      className={itemClassName}
    >
      {item.name}
    </SidebarItem>
  );
}

export function DocsSidebarFolder({
  item,
  level,
  children,
}: {
  item: PageTree.Folder;
  level: number;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const defaultOpen =
    (item.defaultOpen ?? level <= 1) || folderContainsPath(item, pathname);

  return (
    <SidebarFolder defaultOpen={defaultOpen}>
      {item.index ? (
        <SidebarFolderLink
          href={item.index.url}
          external={item.index.external}
          className={itemClassName}
        >
          {item.icon}
          {item.name}
        </SidebarFolderLink>
      ) : (
        <SidebarFolderTrigger className={itemClassName}>
          {item.icon}
          {item.name}
        </SidebarFolderTrigger>
      )}
      <SidebarFolderContent>{children}</SidebarFolderContent>
    </SidebarFolder>
  );
}

export function docsSidebarItemClassName(extra?: string) {
  return cn(itemClassName, extra);
}
