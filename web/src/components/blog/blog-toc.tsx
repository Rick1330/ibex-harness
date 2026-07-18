"use client";

import type { TOCItemType } from "fumadocs-core/server";
import { ListTree } from "lucide-react";

import { TocHeadingList } from "@/components/layout/toc-heading-list";
import { filterTocHeadings } from "@/components/layout/toc-headings";
import {
  TocReadingProgress,
  useReadingProgress,
} from "@/components/layout/toc-reading-progress";

type BlogTocProps = Readonly<{
  items: TOCItemType[];
}>;

function BlogTocRail({ count }: Readonly<{ count: number }>) {
  const progress = useReadingProgress();
  if (count === 0) return null;

  return (
    <div className="blog-toc-rail" aria-hidden>
      <div className="blog-toc-rail-fill" style={{ height: `${progress}%` }} />
    </div>
  );
}

/**
 * Blog/page TOC — plain sticky nav (no fumadocs-ui `Toc` / ScrollArea).
 * Those components assume `#nd-toc` layout and collapse to a hairline outside docs.
 */
export function BlogToc({ items }: BlogTocProps) {
  const headings = filterTocHeadings(items);

  if (headings.length === 0) return null;

  return (
    <nav className="blog-toc" aria-label="On this page">
      <p className="blog-toc-title">
        <ListTree className="size-3.5 shrink-0" strokeWidth={1.5} aria-hidden />
        On this page
      </p>
      <div className="blog-toc-body">
        <BlogTocRail count={headings.length} />
        <TocHeadingList items={headings} className="blog-toc-list" />
      </div>
      <TocReadingProgress className="blog-toc-progress" />
    </nav>
  );
}
