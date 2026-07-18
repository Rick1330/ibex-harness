import type { TOCItemType } from "fumadocs-core/server";
import type { ReactNode } from "react";

import { BlogToc } from "@/components/blog/blog-toc";
import { MobileTocBar } from "@/components/layout/mobile-toc-bar";
import { filterTocHeadings } from "@/components/layout/toc-headings";
import { TocScope } from "@/components/layout/toc-scope";

type ArticleWithTocProps = Readonly<{
  toc: TOCItemType[];
  children: ReactNode;
}>;

/**
 * Blog body + sticky TOC.
 * Fixed-width aside (never `min-width: 0`) so the rail cannot collapse.
 */
export function ArticleWithToc({ toc, children }: ArticleWithTocProps) {
  const headings = filterTocHeadings(toc);

  if (headings.length === 0) {
    return <div className="blog-article-body">{children}</div>;
  }

  return (
    <TocScope items={headings}>
      <div className="blog-article-layout">
        <div className="blog-article-main min-w-0">
          <div className="blog-article-mobile-toc">
            <MobileTocBar items={headings} />
          </div>
          <div className="blog-article-body">{children}</div>
        </div>
        <aside className="blog-article-toc" aria-label="Table of contents">
          <div className="blog-article-toc-sticky">
            <BlogToc items={headings} />
          </div>
        </aside>
      </div>
    </TocScope>
  );
}
