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
import { ListTree } from "lucide-react";
import { useRef } from "react";

import {
  TocReadingProgress,
  useReadingProgress,
} from "@/components/layout/toc-reading-progress";
import { cn } from "@/lib/cn";

type OnThisPageProps = Readonly<{
  items: TOCItemType[];
}>;

function filterHeadings(items: TOCItemType[]): TOCItemType[] {
  return items.filter((item) => item.depth === 2 || item.depth === 3);
}

const linkClassName = cn(
  "block rounded-[4px] border-s-2 border-transparent py-2 pe-2 ps-3 text-[0.8125rem] leading-snug text-text-secondary transition-colors",
  "first:pt-0 last:pb-0 [overflow-wrap:anywhere]",
  "hover:bg-panel-raised hover:text-text-primary",
  "data-[active=true]:border-accent data-[active=true]:bg-panel-raised data-[active=true]:font-medium data-[active=true]:text-text-primary",
);

function OnThisPageItem({
  item,
  index,
  activeIndex,
}: Readonly<{
  item: TOCItemType;
  index: number;
  activeIndex: number;
}>) {
  const isActive = activeIndex === index;
  const isPassed = activeIndex > index;

  return (
    <li className="relative">
      <span
        aria-hidden
        className={cn(
          "absolute top-1/2 z-[1] size-1.5 -translate-y-1/2 rounded-full border border-border bg-canvas transition-colors duration-150",
          item.depth === 3 ? "start-4" : "start-2",
          isActive &&
            "size-2 border-accent bg-accent ring-4 ring-[hsl(var(--border))]",
          isPassed && !isActive && "border-accent bg-accent",
        )}
      />
      <Primitive.TOCItem
        href={item.url}
        className={cn(
          linkClassName,
          item.depth === 3 && "ps-7",
          item.depth === 2 && "ps-5",
        )}
      >
        {item.title}
      </Primitive.TOCItem>
    </li>
  );
}

function TocProgressRail({ count }: Readonly<{ count: number }>) {
  const progress = useReadingProgress();

  if (count === 0) return null;

  return (
    <div
      aria-hidden
      className="pointer-events-none absolute bottom-0 start-0 top-0 w-px bg-border"
    >
      <div
        className="w-full bg-accent transition-[height] duration-150 ease-out"
        style={{ height: `${progress}%` }}
      />
    </div>
  );
}

export function OnThisPage({ items }: OnThisPageProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<HTMLDivElement>(null);
  const headings = filterHeadings(items);
  const activeAnchor = Primitive.useActiveAnchor();
  const activeIndex = headings.findIndex(
    (item) => item.url === `#${activeAnchor}`,
  );

  return (
    <Toc className="docs-toc px-1">
      <p className="docs-toc-header mb-4 flex items-center gap-2 border-b border-border pb-3 text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
        <ListTree className="size-3.5" strokeWidth={1.5} />
        On this page
      </p>
      {headings.length === 0 ? (
        <TocItemsEmpty />
      ) : (
        <ScrollArea className="flex min-h-0 flex-1 flex-col">
          <Primitive.ScrollProvider containerRef={viewRef}>
            <ScrollViewport
              ref={viewRef}
              className="relative max-h-[calc(100dvh-16rem)] text-sm"
            >
              <div ref={containerRef} className="relative ps-2">
                <TocProgressRail count={headings.length} />
                <ul className="relative m-0 list-none space-y-0.5 p-0">
                  {headings.map((item, index) => (
                    <OnThisPageItem
                      activeIndex={activeIndex}
                      index={index}
                      item={item}
                      key={item.url}
                    />
                  ))}
                </ul>
              </div>
            </ScrollViewport>
          </Primitive.ScrollProvider>
          <TocReadingProgress className="mt-4" />
        </ScrollArea>
      )}
    </Toc>
  );
}
