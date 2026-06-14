"use client";

import type { PageTree } from "fumadocs-core/server";
import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo, type ReactNode } from "react";
import { useTreeContext } from "fumadocs-ui/provider";

import { SidebarIcon, getNavIconForUrl } from "@/lib/sidebar-icons";
import { cn } from "@/lib/cn";

type NavPage = {
  name: ReactNode;
  url: string;
};

function isActive(url: string, pathname: string, nested = true) {
  const normalizedUrl = url.endsWith("/") ? url.slice(0, -1) : url;
  const normalizedPath = pathname.endsWith("/")
    ? pathname.slice(0, -1)
    : pathname;

  return (
    normalizedUrl === normalizedPath ||
    (nested && normalizedPath.startsWith(`${normalizedUrl}/`))
  );
}

function scanNavigationList(nodes: PageTree.Node[]): NavPage[] {
  const list: NavPage[] = [];

  nodes.forEach((node) => {
    if (node.type === "folder") {
      if (node.index) list.push(node.index);
      list.push(...scanNavigationList(node.children));
      return;
    }
    if (node.type === "page" && !node.external) {
      list.push(node);
    }
  });

  return list;
}

const cardClassName = cn(
  "flex w-full flex-col gap-2 rounded-md border border-border bg-panel p-4 text-sm",
  "transition-colors hover:bg-panel-raised hover:text-text-primary",
);

const labelClassName =
  "inline-flex items-center gap-1 text-xs font-medium text-text-tertiary";

export function DocsFooterNav() {
  const { root } = useTreeContext();
  const pathname = usePathname();

  const { previous, next } = useMemo(() => {
    const list = scanNavigationList(root.children);
    const index = list.findIndex((item) => isActive(item.url, pathname, false));
    if (index === -1) return {};
    return {
      previous: list[index - 1],
      next: list[index + 1],
    };
  }, [pathname, root.children]);

  if (!previous && !next) return null;

  return (
    <div className="not-prose grid grid-cols-2 gap-4 pb-6">
      {previous ? (
        <Link className={cardClassName} href={previous.url}>
          <span className={labelClassName}>
            <ChevronLeft className="size-4" strokeWidth={1.5} />
            Previous
          </span>
          <span className="inline-flex items-center gap-2 font-medium text-text-primary">
            <SidebarIcon icon={getNavIconForUrl(previous.url)} />
            {previous.name}
          </span>
        </Link>
      ) : (
        <div />
      )}
      {next ? (
        <Link
          className={cn(cardClassName, "col-start-2 text-end")}
          href={next.url}
        >
          <span className={cn(labelClassName, "justify-end")}>
            Next
            <ChevronRight className="size-4" strokeWidth={1.5} />
          </span>
          <span className="inline-flex items-center justify-end gap-2 font-medium text-text-primary">
            {next.name}
            <SidebarIcon icon={getNavIconForUrl(next.url)} />
          </span>
        </Link>
      ) : null}
    </div>
  );
}
