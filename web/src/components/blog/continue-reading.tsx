import Link from "next/link";

import { BlogSectionRule } from "@/components/blog/blog-section-rule";
import { formatBlogDate, type BlogCategory } from "@/lib/blog";

export type ContinuePost = Readonly<{
  url: string;
  title: string;
  date: string;
  category: BlogCategory;
}>;

type ContinueReadingProps = Readonly<{
  prev: ContinuePost | null;
  next: ContinuePost | null;
}>;

/** Prev / next continue strip — DESIGN_GUIDE §14.2. */
export function ContinueReading({ prev, next }: ContinueReadingProps) {
  if (!prev && !next) return null;

  return (
    <section className="blog-continue" aria-labelledby="blog-continue-heading">
      <hr className="blog-hairline" />
      <BlogSectionRule id="blog-continue-heading">Continue reading</BlogSectionRule>
      <div className="blog-continue-grid">
        {prev ? (
          <Link href={prev.url} className="blog-continue-card blog-continue-prev">
            <span className="blog-continue-dir">← Previous</span>
            <span className="blog-continue-title">{prev.title}</span>
            <span className="blog-continue-meta">
              {formatBlogDate(prev.date)} · {prev.category}
            </span>
          </Link>
        ) : (
          <div className="blog-continue-spacer" aria-hidden />
        )}
        {next ? (
          <Link href={next.url} className="blog-continue-card blog-continue-next">
            <span className="blog-continue-dir">Next →</span>
            <span className="blog-continue-title">{next.title}</span>
            <span className="blog-continue-meta">
              {formatBlogDate(next.date)} · {next.category}
            </span>
          </Link>
        ) : (
          <div className="blog-continue-spacer" aria-hidden />
        )}
      </div>
    </section>
  );
}
