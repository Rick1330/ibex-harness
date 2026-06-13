"use client";

import { getBreadcrumbItems } from "fumadocs-core/breadcrumb";
import type { PageTree } from "fumadocs-core/server";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment, useMemo } from "react";

const MAX_LEVELS = 3;

type DocsBreadcrumbProps = {
  tree: PageTree.Root;
};

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
      className="-mb-3 flex flex-row flex-wrap items-center gap-1 text-sm text-text-secondary"
    >
      {items.map((item, index) => (
        <Fragment key={`${String(item.name)}-${index}`}>
          {index > 0 ? (
            <span aria-hidden className="font-mono text-text-tertiary">
              ›
            </span>
          ) : null}
          {item.url ? (
            <Link
              href={item.url}
              className="truncate hover:text-text-primary"
            >
              {item.name}
            </Link>
          ) : (
            <span className="truncate text-text-primary">{item.name}</span>
          )}
        </Fragment>
      ))}
    </nav>
  );
}
