"use client";

import * as Primitive from "fumadocs-core/toc";
import type { TOCItemType } from "fumadocs-core/server";
import type { ReactNode } from "react";

import { filterTocHeadings } from "@/components/layout/toc-headings";

type TocScopeProps = Readonly<{
  items: TOCItemType[];
  children: ReactNode;
}>;

export function TocScope({ items, children }: TocScopeProps) {
  const headings = filterTocHeadings(items);

  if (headings.length === 0) {
    return children;
  }

  return (
    <Primitive.AnchorProvider toc={headings}>{children}</Primitive.AnchorProvider>
  );
}
