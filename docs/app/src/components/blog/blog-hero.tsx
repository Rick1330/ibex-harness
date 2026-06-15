import Link from "next/link";

import type { InferPageType } from "fumadocs-core/source";

import type { blogSource } from "@/lib/source";

type BlogPage = InferPageType<typeof blogSource>;

type BlogHeroProps = Readonly<{
  featured?: BlogPage;
}>;

export function BlogHero({ featured }: BlogHeroProps) {
  return (
    <header className="mb-12 border-b border-border pb-10">
      <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
        Engineering Notes
      </p>
      <h1 className="mb-4 text-4xl font-bold tracking-tight text-foreground md:text-5xl">
        From the IBEX team
      </h1>
      <p className="max-w-2xl text-lg leading-relaxed text-muted-foreground">
        Architecture deep-dives, launch notes, and practical guides for building
        with IBEX Harness.
      </p>
      {featured ? (
        <div className="mt-8 rounded-xl border border-border bg-gradient-to-br from-muted/30 to-card p-6 md:p-8">
          <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Featured
          </p>
          <Link href={featured.url} className="group block space-y-3">
            <h2 className="text-2xl font-bold tracking-tight text-foreground transition-opacity group-hover:opacity-80 md:text-3xl">
              {featured.data.title}
            </h2>
            {featured.data.excerpt ? (
              <p className="max-w-2xl text-base leading-relaxed text-muted-foreground">
                {featured.data.excerpt}
              </p>
            ) : null}
            <span className="inline-flex items-center gap-1 text-sm font-medium text-foreground">
              Read featured post{" "}
              <span className="transition-transform group-hover:translate-x-0.5">→</span>
            </span>
          </Link>
        </div>
      ) : null}
    </header>
  );
}
