"use client";

import * as Primitive from "fumadocs-core/toc";
import type { TOCItemType } from "fumadocs-core/server";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "fumadocs-ui/components/ui/collapsible";
import { ChevronDown, ListTree } from "lucide-react";
import { useState } from "react";

import { TocHeadingList } from "@/components/layout/toc-heading-list";
import { filterTocHeadings } from "@/components/layout/toc-headings";
import { cn } from "@/lib/cn";

type MobileTocBarProps = Readonly<{
  items: TOCItemType[];
}>;

export function MobileTocBar({ items }: MobileTocBarProps) {
  const headings = filterTocHeadings(items);
  const [open, setOpen] = useState(false);
  const activeAnchor = Primitive.useActiveAnchor();

  if (headings.length === 0) return null;

  const activeHeading = headings.find(
    (item) => item.url === `#${activeAnchor}`,
  );
  const activeTitle = activeHeading ? activeHeading.title : headings[0].title;

  return (
    <div className="mobile-toc-bar has-mobile-toc-bar mb-6 lg:hidden">
      <Collapsible open={open} onOpenChange={setOpen}>
        <CollapsibleTrigger
          className={cn(
            "flex w-full min-h-[var(--mobile-toc-bar-height,2.75rem)] items-center gap-2",
            "border-b border-border bg-canvas px-1 py-2 text-start",
            "sticky top-[var(--site-nav-height)] z-40",
          )}
        >
          <ListTree
            className="size-3.5 shrink-0 text-text-tertiary"
            strokeWidth={1.5}
          />
          <span className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
            On this page
          </span>
          {activeTitle ? (
            <span className="min-w-0 flex-1 truncate text-sm text-text-secondary">
              {activeTitle}
            </span>
          ) : null}
          <ChevronDown
            className={cn(
              "size-4 shrink-0 text-text-secondary transition-transform",
              open && "rotate-180",
            )}
          />
        </CollapsibleTrigger>
        <CollapsibleContent
          className={cn(
            "mobile-toc-bar-panel border-b border-border bg-canvas px-2 py-2",
            "[&_[class*='animate-fd-collapsible']]:!animate-none",
          )}
        >
          <TocHeadingList
            compact
            items={items}
            onItemClick={() => { setOpen(false); }}
          />
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
