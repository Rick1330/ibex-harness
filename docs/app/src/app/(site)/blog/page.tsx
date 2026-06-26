import type { Metadata } from "next";

import { BlogHero } from "@/components/blog/blog-hero";
import { BlogPostList } from "@/components/blog/blog-post-list";
import { blogSource } from "@/lib/source";

export const metadata: Metadata = {
  title: "Engineering Notes",
  description:
    "Updates, guides, and deep-dives from the team building IBEX Harness.",
};

export default function BlogPage() {
  const posts = blogSource
    .getPages()
    .sort(
      (a, b) =>
        new Date(String(b.data.date)).getTime() -
        new Date(String(a.data.date)).getTime(),
    );

  const featured =
    posts.find((p) => p.data.featured === true) ?? posts[0];
  const rest = posts.filter((p) => p.url !== featured?.url);

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 md:px-6 md:py-16 lg:px-8">
      <BlogHero featured={featured} />
      <BlogPostList
        posts={rest.map((post) => ({
          url: post.url,
          data: {
            title: post.data.title,
            date: String(post.data.date),
            excerpt: post.data.excerpt,
            tags: post.data.tags,
            readingTime: post.data.readingTime as string | undefined,
            author: post.data.author,
            authorUrl: post.data.authorUrl as string | undefined,
          },
        }))}
      />
    </div>
  );
}
