"use client";

import * as Primitive from "fumadocs-core/toc";
import type { TOCItemType } from "fumadocs-core/server";

import { filterTocHeadings } from "@/components/layout/toc-headings";
import { cn } from "@/lib/cn";

export const tocLinkClassName = cn(
  "block rounded-[4px] border-s-2 border-transparent py-2 pe-2 ps-3 text-[0.8125rem] leading-snug text-text-secondary transition-colors",
  "first:pt-0 last:pb-0 [overflow-wrap:anywhere]",
  "hover:bg-panel-raised hover:text-text-primary",
  "data-[active=true]:border-accent data-[active=true]:bg-panel-raised data-[active=true]:font-medium data-[active=true]:text-text-primary",
);

type TocHeadingItemProps = Readonly<{
  item: TOCItemType;
  index: number;
  activeIndex: number;
  compact?: boolean;
}>;

export function TocHeadingItem({
  item,
  index,
  activeIndex,
  compact = false,
}: TocHeadingItemProps) {
  const isActive = activeIndex === index;
  const isPassed = activeIndex > index;

  return (
    <li className="relative">
      {!compact ? (
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
      ) : null}
      <Primitive.TOCItem
        href={item.url}
        className={cn(
          tocLinkClassName,
          item.depth === 3 && (compact ? "ps-5" : "ps-7"),
          item.depth === 2 && (compact ? "ps-3" : "ps-5"),
          compact && "py-1.5 text-sm",
        )}
      >
        {item.title}
      </Primitive.TOCItem>
    </li>
  );
}

type TocHeadingListProps = Readonly<{
  items: TOCItemType[];
  compact?: boolean;
  className?: string;
}>;

export function TocHeadingList({
  items,
  compact = false,
  className,
}: TocHeadingListProps) {
  const headings = filterTocHeadings(items);
  const activeAnchor = Primitive.useActiveAnchor();
  const activeIndex = headings.findIndex(
    (item) => item.url === `#${activeAnchor}`,
  );

  if (headings.length === 0) return null;

  return (
    <ul className={cn("relative m-0 list-none space-y-0.5 p-0", className)}>
      {headings.map((item, index) => (
        <TocHeadingItem
          activeIndex={activeIndex}
          compact={compact}
          index={index}
          item={item}
          key={item.url}
        />
      ))}
    </ul>
  );
}
