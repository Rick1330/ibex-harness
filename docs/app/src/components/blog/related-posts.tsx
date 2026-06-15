import type { InferPageType } from "fumadocs-core/source";

import { PostCard } from "@/components/blog/post-card";
import type { blogSource } from "@/lib/source";

type BlogPage = InferPageType<typeof blogSource>;

type RelatedPostsProps = Readonly<{
  posts: BlogPage[];
  currentUrl: string;
}>;

export function RelatedPosts({ posts, currentUrl }: RelatedPostsProps) {
  const related = posts.filter((p) => p.url !== currentUrl).slice(0, 3);
  if (related.length === 0) return null;

  return (
    <section className="mt-16 border-t border-border pt-10">
      <h2 className="mb-6 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
        More to read
      </h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {related.map((post) => (
          <PostCard
            key={post.url}
            url={post.url}
            title={post.data.title}
            date={String(post.data.date)}
            excerpt={post.data.excerpt}
            tags={post.data.tags}
          readingTime={post.data.readingTime as string | undefined}
          author={post.data.author}
          authorUrl={post.data.authorUrl as string | undefined}
        />
        ))}
      </div>
    </section>
  );
}
