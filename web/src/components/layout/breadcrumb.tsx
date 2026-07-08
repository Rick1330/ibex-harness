"use client";

import { getBreadcrumbItems } from "fumadocs-core/breadcrumb";
import type { PageTree } from "fumadocs-core/server";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment, useMemo } from "react";

import { SidebarIcon, getNavIconForUrl, toNavUrl } from "@/lib/sidebar-icons";

const MAX_LEVELS = 3;

type DocsBreadcrumbProps = Readonly<{
  tree: PageTree.Root;
}>;

export function DocsBreadcrumb({ tree }: DocsBreadcrumbProps) {
  const pathname = usePathname();

  const items = useMemo(() => {
    const trail = getBreadcrumbItems(pathname, tree, { includePage: true });
    return trail.length > MAX_LEVELS ? trail.slice(-MAX_LEVELS) : trail;
  }, [pathname, tree]);

  if (items.length === 0) return null;

  return (
    <nav
      aria-label="Breadcrumb"
      className="mb-6 flex flex-row flex-wrap items-center gap-1.5 text-sm text-text-secondary"
    >
      {items.map((item, index) => {
        const Icon = item.url ? getNavIconForUrl(toNavUrl(item.url)) : null;

        return (
          <Fragment key={`${String(item.name)}-${index}`}>
            {index > 0 ? (
              <span aria-hidden className="font-mono text-text-tertiary">
                ›
              </span>
            ) : null}
            {item.url ? (
              <Link
                className="inline-flex max-w-full items-center gap-1.5 truncate hover:text-text-primary"
                href={item.url}
              >
                {Icon ? <SidebarIcon icon={Icon} /> : null}
                <span className="truncate">{item.name}</span>
              </Link>
            ) : (
              <span className="inline-flex max-w-full items-center gap-1.5 truncate text-text-primary">
                {Icon ? <SidebarIcon icon={Icon} /> : null}
                <span className="truncate">{item.name}</span>
              </span>
            )}
          </Fragment>
        );
      })}
    </nav>
  );
}
