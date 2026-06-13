"use client";

import * as Primitive from "fumadocs-core/toc";
import type { TOCItemType } from "fumadocs-core/server";
import {
  Toc,
  TocItemsEmpty,
} from "fumadocs-ui/components/layout/toc";
import {
  ScrollArea,
  ScrollViewport,
} from "fumadocs-ui/components/ui/scroll-area";
import { useRef } from "react";

import { cn } from "@/lib/cn";

type OnThisPageProps = {
  items: TOCItemType[];
};

function filterHeadings(items: TOCItemType[]): TOCItemType[] {
  return items.filter((item) => item.depth === 2 || item.depth === 3);
}

const linkClassName = cn(
  "block border-l border-transparent py-1.5 text-sm text-text-secondary transition-colors",
  "first:pt-0 last:pb-0 [overflow-wrap:anywhere]",
  "hover:text-text-primary data-[active=true]:border-accent data-[active=true]:text-text-primary",
);

function OnThisPageItem({ item }: { item: TOCItemType }) {
  return (
    <Primitive.TOCItem
      href={item.url}
      className={cn(
        linkClassName,
        item.depth === 3 && "ps-5",
        item.depth === 2 && "ps-3",
      )}
    >
      {item.title}
    </Primitive.TOCItem>
  );
}

export function OnThisPage({ items }: OnThisPageProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<HTMLDivElement>(null);
  const headings = filterHeadings(items);

  return (
    <Toc>
      <p className="text-sm font-medium text-text-primary">On this page</p>
      {headings.length === 0 ? (
        <TocItemsEmpty />
      ) : (
        <ScrollArea className="flex min-h-0 flex-1 flex-col">
          <Primitive.ScrollProvider containerRef={viewRef}>
            <ScrollViewport
              ref={viewRef}
              className="relative max-h-[calc(100dvh-12rem)] text-sm"
            >
              <div ref={containerRef} className="flex flex-col">
                {headings.map((item) => (
                  <OnThisPageItem item={item} key={item.url} />
                ))}
              </div>
            </ScrollViewport>
          </Primitive.ScrollProvider>
        </ScrollArea>
      )}
    </Toc>
  );
}
