"use client";

import * as Primitive from "fumadocs-core/toc";
import type { TOCItemType } from "fumadocs-core/toc";
import { TOCEmpty } from "fumadocs-ui/components/toc/default";
import { ListTree } from "lucide-react";
import { useRef, type ReactNode } from "react";

import { TocHeadingList } from "@/components/layout/toc-heading-list";
import { filterTocHeadings } from "@/components/layout/toc-headings";
import {
  TocReadingProgress,
  useReadingProgress,
} from "@/components/layout/toc-reading-progress";
import { cn } from "@/lib/cn";

type OnThisPageProps = Readonly<{
  items: TOCItemType[];
}>;

function Toc({
  className,
  children,
}: Readonly<{ className?: string; children: ReactNode }>) {
  return <div className={cn("flex min-h-0 flex-col", className)}>{children}</div>;
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
  const headings = filterTocHeadings(items);

  return (
    <Toc className="docs-toc px-1">
      <p className="docs-toc-header mb-4 flex items-center gap-2 border-b border-border pb-3 text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
        <ListTree className="size-3.5" strokeWidth={1.5} />
        On this page
      </p>
      {headings.length === 0 ? (
        <TOCEmpty />
      ) : (
        <div className="flex min-h-0 flex-1 flex-col">
          <Primitive.ScrollProvider containerRef={viewRef}>
            <div
              ref={viewRef}
              className="relative max-h-[calc(100dvh-16rem)] overflow-y-auto text-sm"
            >
              <div ref={containerRef} className="relative ps-2">
                <TocProgressRail count={headings.length} />
                <TocHeadingList items={items} />
              </div>
            </div>
          </Primitive.ScrollProvider>
          <TocReadingProgress className="mt-4" />
        </div>
      )}
    </Toc>
  );
}
