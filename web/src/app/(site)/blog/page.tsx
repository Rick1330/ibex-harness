import type { Metadata } from "next";

import { BlogIndex } from "@/components/blog/blog-index";
import { resolveBlogCategory, type BlogIndexItem } from "@/lib/blog";
import { blogSource } from "@/lib/source";

export const metadata: Metadata = {
  title: "Blog",
  description:
    "Long-form writing about agent infrastructure, memory, and running LLMs in production.",
  alternates: {
    types: {
      "application/rss+xml": "/blog/rss.xml",
    },
  },
};

function toIndexItem(post: {
  url: string;
  data: {
    title: string;
    date: string | Date;
    excerpt?: string;
    tags?: string[];
    readingTime?: unknown;
    author?: string;
    authorUrl?: unknown;
  };
}): BlogIndexItem {
  return {
    url: post.url,
    title: post.data.title,
    date: String(post.data.date),
    excerpt: post.data.excerpt,
    tags: post.data.tags,
    readingTime:
      typeof post.data.readingTime === "string"
        ? post.data.readingTime
        : undefined,
    author: post.data.author,
    authorUrl:
      typeof post.data.authorUrl === "string"
        ? post.data.authorUrl
        : undefined,
    category: resolveBlogCategory(post.data.tags),
  };
}

export default function BlogPage() {
  const pages = blogSource
    .getPages()
    .sort(
      (a, b) =>
        new Date(String(b.data.date)).getTime() -
        new Date(String(a.data.date)).getTime(),
    );

  const items = pages.map(toIndexItem);
  const featuredPage =
    pages.find((p) => p.data.featured === true) ?? pages[0];
  const featured = featuredPage ? toIndexItem(featuredPage) : null;

  return (
    <div className="blog-page">
      <header className="blog-index-intro">
        <h1 className="blog-index-title">Blog</h1>
        <p className="blog-index-lede">
          Long-form writing about agent infrastructure, memory, and running LLMs
          in production.
        </p>
      </header>
      <BlogIndex featured={featured} posts={items} />
    </div>
  );
}
