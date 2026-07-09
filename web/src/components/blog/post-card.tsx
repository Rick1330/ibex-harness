import Link from "next/link";

type PostCardProps = Readonly<{
  url: string;
  title: string;
  date: string;
  excerpt?: string;
  tags?: string[];
  readingTime?: string;
  author?: string;
  authorUrl?: string;
}>;

export function PostCard({
  url,
  title,
  date,
  excerpt,
  tags,
  readingTime,
  author,
  authorUrl,
}: PostCardProps) {
  return (
    <article className="group flex h-full flex-col rounded-xl border border-border bg-card p-5 transition-colors hover:bg-muted/20">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <time className="font-medium tabular-nums">
          {new Date(date).toLocaleDateString("en-US", {
            year: "numeric",
            month: "short",
            day: "numeric",
          })}
        </time>
        {readingTime ? (
          <>
            <span>·</span>
            <span>{readingTime}</span>
          </>
        ) : null}
        {author ? (
          <>
            <span>·</span>
            {authorUrl ? (
              <Link
                href={authorUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium text-foreground transition-opacity hover:opacity-80"
              >
                {author}
              </Link>
            ) : (
              <span>{author}</span>
            )}
          </>
        ) : null}
      </div>
      <Link href={url} className="flex flex-1 flex-col">
        <h2 className="mb-2 text-lg font-semibold leading-snug text-foreground group-hover:underline">
          {title}
        </h2>
        {excerpt ? (
          <p className="mb-4 line-clamp-3 flex-1 text-sm leading-relaxed text-muted-foreground">
            {excerpt}
          </p>
        ) : (
          <div className="flex-1" />
        )}
        {tags && tags.length > 0 ? (
          <div className="mb-3 flex flex-wrap gap-1.5">
            {tags.map((tag) => (
              <span
                key={tag}
                className="rounded-full border border-border bg-muted/30 px-2 py-0.5 text-[11px] font-medium text-muted-foreground"
              >
                {tag}
              </span>
            ))}
          </div>
        ) : null}
        <span className="mt-auto inline-flex items-center gap-1 text-sm font-medium text-muted-foreground transition-colors group-hover:text-foreground">
          Read post{" "}
          <span className="transition-transform group-hover:translate-x-0.5">→</span>
        </span>
      </Link>
    </article>
  );
}
