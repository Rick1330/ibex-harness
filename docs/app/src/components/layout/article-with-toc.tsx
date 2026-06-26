import type { TOCItemType } from "fumadocs-core/server";
import type { ReactNode } from "react";

import { MobileTocBar } from "@/components/layout/mobile-toc-bar";
import { OnThisPage } from "@/components/layout/toc";
import { TocScope } from "@/components/layout/toc-scope";

type ArticleWithTocProps = Readonly<{
  toc: TOCItemType[];
  children: ReactNode;
}>;

export function ArticleWithToc({ toc, children }: ArticleWithTocProps) {
  if (toc.length === 0) {
    return <>{children}</>;
  }

  return (
    <TocScope items={toc}>
      <div className="lg:grid lg:grid-cols-[minmax(0,42rem)_14rem] lg:gap-12 lg:justify-center">
        <div className="min-w-0">
          <MobileTocBar items={toc} />
          {children}
        </div>
        <aside className="hidden lg:block">
          <div className="sticky top-[calc(var(--site-nav-height)+1.5rem)]">
            <OnThisPage items={toc} />
          </div>
        </aside>
      </div>
    </TocScope>
  );
}
