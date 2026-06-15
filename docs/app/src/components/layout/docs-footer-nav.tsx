"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo } from "react";
import { useTreeContext } from "fumadocs-ui/provider";

import { SidebarIcon, getNavIconForUrl, toNavUrl } from "@/lib/sidebar-icons";
import {
  adjacentNavPages,
  flattenPageTree,
  navUrlsMatch,
} from "@/lib/sidebar-nav-pages";
import { cn } from "@/lib/cn";

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
    const pages = flattenPageTree(root.children);
    return adjacentNavPages(pages, pathname);
  }, [pathname, root.children]);

  if (!previous && !next) return null;

  return (
    <div className="not-prose grid grid-cols-2 gap-4 pb-6">
      {previous && !navUrlsMatch(previous.url, pathname) ? (
        <Link className={cardClassName} href={previous.url} prefetch scroll={false}>
          <span className={labelClassName}>
            <ChevronLeft className="size-4" strokeWidth={1.5} />
            Previous
          </span>
          <span className="inline-flex items-center gap-2 font-medium text-text-primary">
            <SidebarIcon icon={getNavIconForUrl(toNavUrl(previous.url))} />
            {previous.name}
          </span>
        </Link>
      ) : (
        <div />
      )}
      {next && !navUrlsMatch(next.url, pathname) ? (
        <Link
          className={cn(cardClassName, "col-start-2 text-end")}
          href={next.url}
          prefetch
          scroll={false}
        >
          <span className={cn(labelClassName, "justify-end")}>
            Next
            <ChevronRight className="size-4" strokeWidth={1.5} />
          </span>
          <span className="inline-flex items-center justify-end gap-2 font-medium text-text-primary">
            {next.name}
            <SidebarIcon icon={getNavIconForUrl(toNavUrl(next.url))} />
          </span>
        </Link>
      ) : null}
    </div>
  );
}
