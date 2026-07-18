import Link from "next/link";

import { BlogSectionRule } from "@/components/blog/blog-section-rule";
import {
  formatBlogDate,
  titleWithItalicTail,
  type BlogIndexItem,
} from "@/lib/blog";

type FeaturedPostProps = Readonly<{
  post: BlogIndexItem;
}>;

/** Featured strip — typography + hairline, no card chrome (DESIGN_GUIDE §14.1). */
export function FeaturedPost({ post }: FeaturedPostProps) {
  const { lead, italic } = titleWithItalicTail(post.title);

  return (
    <section className="blog-featured" aria-labelledby="blog-featured-heading">
      <BlogSectionRule id="blog-featured-heading">Featured</BlogSectionRule>
      <p className="blog-meta">
        <time dateTime={post.date}>{formatBlogDate(post.date)}</time>
        <span aria-hidden>·</span>
        <span className="blog-meta-accent">{post.category}</span>
        {post.readingTime ? (
          <>
            <span aria-hidden>·</span>
            <span>{post.readingTime}</span>
          </>
        ) : null}
      </p>
      <Link href={post.url} className="blog-featured-title group">
        <h2 className="blog-featured-heading">
          {lead ? <>{lead} </> : null}
          <em className="italic">{italic}</em>
        </h2>
        <span className="blog-featured-arrow" aria-hidden>
          →
        </span>
      </Link>
      {post.excerpt ? (
        <p className="blog-featured-excerpt">{post.excerpt}</p>
      ) : null}
      <Link href={post.url} className="blog-featured-cta">
        Read the piece{" "}
        <span aria-hidden>→</span>
      </Link>
    </section>
  );
}
