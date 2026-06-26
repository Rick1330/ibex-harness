import type { TOCItemType } from "fumadocs-core/server";
import type { ReactNode } from "react";

import { MobileTocBar } from "@/components/layout/mobile-toc-bar";
import { OnThisPage } from "@/components/layout/toc";
import { filterTocHeadings } from "@/components/layout/toc-headings";
import { TocScope } from "@/components/layout/toc-scope";

type ArticleWithTocProps = Readonly<{
  toc: TOCItemType[];
  children: ReactNode;
}>;

export function ArticleWithToc({ toc, children }: ArticleWithTocProps) {
  const headings = filterTocHeadings(toc);

  if (headings.length === 0) {
    return <>{children}</>;
  }

  return (
    <TocScope items={headings}>
      <div className="lg:grid lg:grid-cols-[minmax(0,42rem)_14rem] lg:gap-12 lg:justify-center">
        <div className="min-w-0">
          <MobileTocBar items={headings} />
          {children}
        </div>
        <aside className="hidden lg:block">
          <div className="sticky top-[calc(var(--site-nav-height)+1.5rem)]">
            <OnThisPage items={headings} />
          </div>
        </aside>
      </div>
    </TocScope>
  );
}
