import Link from "next/link";

import { GithubIcon } from "@/components/icons/github-icon";
import {
  formatBlogDate,
  titleWithItalicTail,
  type BlogCategory,
} from "@/lib/blog";

type BlogPostHeaderProps = Readonly<{
  title: string;
  date: string;
  category: BlogCategory;
  author?: string;
  authorUrl?: string;
  readingTime?: string;
}>;

function authorInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  const first = parts[0].charAt(0);
  const second = parts[1].charAt(0);
  return `${first}${second}`.toUpperCase();
}

/** Post header per DESIGN_GUIDE §14.2 — back link, mono meta, display H1, byline. */
export function BlogPostHeader({
  title,
  date,
  category,
  author,
  authorUrl,
  readingTime,
}: BlogPostHeaderProps) {
  const { lead, italic } = titleWithItalicTail(title);

  return (
    <header className="blog-post-header">
      <Link href="/blog" className="blog-back-link">
        ← Back to blog
      </Link>

      <p className="blog-meta">
        <time dateTime={date}>{formatBlogDate(date)}</time>
        <span aria-hidden>·</span>
        <span className="blog-meta-accent">{category}</span>
        {readingTime ? (
          <>
            <span aria-hidden>·</span>
            <span>{readingTime}</span>
          </>
        ) : null}
      </p>

      <h1 className="blog-post-title">
        {lead ? <>{lead} </> : null}
        <em className="italic">{italic}</em>
      </h1>

      {author ? (
        <div className="blog-byline">
          <span className="blog-byline-avatar" aria-hidden>
            {authorInitials(author)}
          </span>
          <span className="blog-byline-prefix">by</span>
          {authorUrl ? (
            <Link
              href={authorUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="blog-byline-author"
            >
              {author}
              <GithubIcon className="size-3.5" strokeWidth={1.5} />
            </Link>
          ) : (
            <span className="blog-byline-author-plain">{author}</span>
          )}
        </div>
      ) : null}

      <hr className="blog-hairline" />
    </header>
  );
}
