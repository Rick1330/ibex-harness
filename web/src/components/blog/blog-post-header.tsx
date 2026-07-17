import Link from "next/link";

import { GithubIcon } from "@/components/icons/github-icon";

type BlogPostHeaderProps = Readonly<{
  title: string;
  date: string;
  author?: string;
  authorUrl?: string;
  tags?: string[];
  readingTime?: string;
}>;

export function BlogPostHeader({
  title,
  date,
  author,
  authorUrl,
  tags,
  readingTime,
}: BlogPostHeaderProps) {
  return (
    <header className="mb-10 border-b border-border pb-8">
      <p className="mb-4 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
        Engineering Notes
      </p>
      <h1 className="mb-5 text-3xl font-bold tracking-tight text-foreground md:text-4xl lg:text-[2.75rem] lg:leading-tight">
        {title}
      </h1>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-muted-foreground">
        <time className="tabular-nums">
          {new Date(date).toLocaleDateString("en-US", {
            year: "numeric",
            month: "long",
            day: "numeric",
          })}
        </time>
        {author ? (
          <>
            <span>·</span>
            {authorUrl ? (
              <Link
                href={authorUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 font-medium text-foreground transition-opacity hover:opacity-80"
              >
                {author}
                <GithubIcon className="size-3.5" strokeWidth={1.5} />
              </Link>
            ) : (
              <span>{author}</span>
            )}
          </>
        ) : null}
        {readingTime ? (
          <>
            <span>·</span>
            <span>{readingTime}</span>
          </>
        ) : null}
      </div>
      {tags && tags.length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {tags.map((tag) => (
            <span
              key={tag}
              className="rounded-full border border-border bg-muted/30 px-2.5 py-0.5 text-xs font-medium text-muted-foreground"
            >
              {tag}
            </span>
          ))}
        </div>
      ) : null}
    </header>
  );
}
