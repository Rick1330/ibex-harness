import Link from "next/link";

import { BlogSectionRule } from "@/components/blog/blog-section-rule";
import {
  formatBlogDate,
  groupPostsByYear,
  type BlogIndexItem,
} from "@/lib/blog";

type BlogArchiveProps = Readonly<{
  posts: ReadonlyArray<BlogIndexItem>;
}>;

/** Year-grouped archive rows — date · category · title (no excerpts). */
export function BlogArchive({ posts }: BlogArchiveProps) {
  const groups = groupPostsByYear(posts);

  if (groups.length === 0) {
    return (
      <p className="blog-archive-empty">No posts match this filter.</p>
    );
  }

  return (
    <section className="blog-archive" aria-labelledby="blog-archive-heading">
      <BlogSectionRule id="blog-archive-heading">Archive</BlogSectionRule>
      {groups.map(({ year, posts: yearPosts }) => (
        <div key={year} className="blog-archive-year">
          <h3 className="blog-archive-year-label">{year}</h3>
          <ul className="blog-archive-list">
            {yearPosts.map((post) => (
              <li key={post.url} className="blog-archive-row">
                <time
                  className="blog-archive-date"
                  dateTime={post.date}
                >
                  {formatBlogDate(post.date)}
                </time>
                <span className="blog-archive-category">{post.category}</span>
                <Link href={post.url} className="blog-archive-title">
                  {post.title}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
