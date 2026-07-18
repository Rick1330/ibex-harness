"use client";

import { cn } from "@/lib/cn";
import {
  BLOG_CATEGORIES,
  type BlogCategory,
} from "@/lib/blog";

type CategoryFilterProps = Readonly<{
  active: BlogCategory | null;
  onChange: (category: BlogCategory | null) => void;
  className?: string;
}>;

/** Editorial category chips — All / Engineering / Product / Research. */
export function CategoryFilter({
  active,
  onChange,
  className,
}: CategoryFilterProps) {
  return (
    <div className={cn("blog-category-filter", className)}>
      <button
        type="button"
        aria-pressed={active === null}
        onClick={() => {
          onChange(null);
        }}
        className={cn(
          "blog-category-chip",
          active === null && "blog-category-chip-active",
        )}
      >
        All
      </button>
      {BLOG_CATEGORIES.map((category) => (
        <button
          key={category}
          type="button"
          aria-pressed={active === category}
          onClick={() => {
            onChange(category === active ? null : category);
          }}
          className={cn(
            "blog-category-chip",
            active === category && "blog-category-chip-active",
          )}
        >
          {category}
        </button>
      ))}
    </div>
  );
}
