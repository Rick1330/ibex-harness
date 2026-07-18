"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo, type ReactNode } from "react";
import { useTreeContext } from "fumadocs-ui/provider";

import { getNavIconForUrl, toNavUrl } from "@/lib/sidebar-icons";
import {
  adjacentNavPages,
  flattenPageTree,
  navUrlsMatch,
  type NavPage,
} from "@/lib/sidebar-nav-pages";
import { cn } from "@/lib/cn";

const cardClassName = cn(
  "flex w-full flex-col gap-2 rounded-md border border-border bg-panel p-4 text-sm",
  "transition-colors hover:bg-panel-raised hover:text-text-primary",
);

const labelClassName =
  "inline-flex items-center gap-1 text-xs font-medium text-text-tertiary";

function PageIcon({ url }: Readonly<{ url: string }>): ReactNode {
  const Icon = getNavIconForUrl(toNavUrl(url));
  if (!Icon) return null;
  return (
    <Icon
      aria-hidden
      className="size-4 shrink-0 text-text-primary"
      strokeWidth={1.5}
    />
  );
}

function PreviousCard({ page }: Readonly<{ page: NavPage }>) {
  return (
    <Link className={cardClassName} href={page.url} prefetch scroll={false}>
      <span className={labelClassName}>
        <ChevronLeft className="size-4" strokeWidth={1.5} />
        Previous
      </span>
      <span className="inline-flex items-center gap-2 font-medium text-text-primary">
        <PageIcon url={page.url} />
        {page.name}
      </span>
    </Link>
  );
}

function NextCard({ page }: Readonly<{ page: NavPage }>) {
  return (
    <Link
      className={cn(cardClassName, "sm:col-start-2 text-end")}
      href={page.url}
      prefetch
      scroll={false}
    >
      <span className={cn(labelClassName, "justify-end")}>
        Next
        <ChevronRight className="size-4" strokeWidth={1.5} />
      </span>
      <span className="inline-flex items-center justify-end gap-2 font-medium text-text-primary">
        {page.name}
        <PageIcon url={page.url} />
      </span>
    </Link>
  );
}

export function DocsFooterNav() {
  const { root } = useTreeContext();
  const pathname = usePathname();

  const { previous, next } = useMemo(() => {
    const pages = flattenPageTree(root.children);
    return adjacentNavPages(pages, pathname);
  }, [pathname, root.children]);

  if (!previous && !next) return null;

  return (
    <div className="not-prose grid grid-cols-1 gap-4 pb-6 sm:grid-cols-2">
      {previous && !navUrlsMatch(previous.url, pathname) ? (
        <PreviousCard page={previous} />
      ) : (
        <div />
      )}
      {next && !navUrlsMatch(next.url, pathname) ? (
        <NextCard page={next} />
      ) : null}
    </div>
  );
}
