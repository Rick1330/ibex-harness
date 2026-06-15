"use client";

import { cn } from "@/lib/cn";

type TagFilterProps = Readonly<{
  tags: string[];
  active: string | null;
  onChange: (tag: string | null) => void;
  className?: string;
}>;

export function TagFilter({ tags, active, onChange, className }: TagFilterProps) {
  if (tags.length === 0) return null;

  return (
    <div className={cn("mb-8 flex flex-wrap gap-2", className)}>
      <button
        type="button"
        onClick={() => { onChange(null); }}
        className={cn(
          "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
          active === null
            ? "border-foreground bg-foreground text-background"
            : "border-border bg-card text-muted-foreground hover:bg-muted/30",
        )}
      >
        All
      </button>
      {tags.map((tag) => (
        <button
          key={tag}
          type="button"
          onClick={() => { onChange(tag === active ? null : tag); }}
          className={cn(
            "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
            active === tag
              ? "border-foreground bg-foreground text-background"
              : "border-border bg-card text-muted-foreground hover:bg-muted/30",
          )}
        >
          {tag}
        </button>
      ))}
    </div>
  );
}
