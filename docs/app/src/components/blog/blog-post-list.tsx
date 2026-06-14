"use client";

import { useMemo, useState } from "react";

import { PostGrid } from "@/components/blog/post-grid";
import { TagFilter } from "@/components/blog/tag-filter";

type BlogPostItem = {
  url: string;
  data: {
    title: string;
    date: string;
    excerpt?: string;
    tags?: string[];
    readingTime?: string;
    author?: string;
    authorUrl?: string;
  };
};

type BlogPostListProps = Readonly<{
  posts: BlogPostItem[];
}>;

export function BlogPostList({ posts }: BlogPostListProps) {
  const [activeTag, setActiveTag] = useState<string | null>(null);

  const tags = useMemo(() => {
    const set = new Set<string>();
    for (const post of posts) {
      post.data.tags?.forEach((tag) => set.add(tag));
    }
    return [...set].sort((a, b) => a.localeCompare(b));
  }, [posts]);

  const filtered = useMemo(() => {
    if (!activeTag) return posts;
    return posts.filter((post) => post.data.tags?.includes(activeTag));
  }, [posts, activeTag]);

  return (
    <>
      <TagFilter
        tags={tags}
        active={activeTag}
        onChange={setActiveTag}
      />
      <PostGrid posts={filtered} />
    </>
  );
}
