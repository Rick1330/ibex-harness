"use client";

import { useMemo, useState } from "react";

import { BlogArchive } from "@/components/blog/blog-archive";
import { CategoryFilter } from "@/components/blog/category-filter";
import { FeaturedPost } from "@/components/blog/featured-post";
import type { BlogCategory, BlogIndexItem } from "@/lib/blog";

type BlogIndexProps = Readonly<{
  featured: BlogIndexItem | null;
  posts: BlogIndexItem[];
}>;

/** Client index: category chips + featured + year archive. */
export function BlogIndex({ featured, posts }: BlogIndexProps) {
  const [active, setActive] = useState<BlogCategory | null>(null);

  const filteredArchive = useMemo(() => {
    const base = posts.filter((post) =>
      featured ? post.url !== featured.url : true,
    );
    if (!active) return base;
    return base.filter((post) => post.category === active);
  }, [posts, featured, active]);

  const featuredVisible =
    featured && (!active || featured.category === active) ? featured : null;

  return (
    <>
      <CategoryFilter active={active} onChange={setActive} />
      {featuredVisible ? <FeaturedPost post={featuredVisible} /> : null}
      <BlogArchive posts={filteredArchive} />
    </>
  );
}
