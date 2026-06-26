"use client";

import { SearchIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { Kbd } from "@/components/mdx/kbd";
import { cn } from "@/lib/cn";
import { useSearchContext } from "fumadocs-ui/provider";

type NavSearchProps = Readonly<{
  className?: string;
}>;

export function NavSearch({ className }: NavSearchProps) {
  const { setOpenSearch, enabled } = useSearchContext();
  const [modifier, setModifier] = useState("⌘");

  useEffect(() => {
    setModifier(
      window.navigator.userAgent.includes("Windows") ? "Ctrl" : "⌘",
    );
  }, []);

  if (!enabled) return null;

  return (
    <button
      type="button"
      data-search-full=""
      aria-label="Open search"
      className={cn(
        "inline-flex h-9 w-full items-center gap-2 rounded-[6px] border border-border",
        "bg-panel px-3 text-sm text-text-secondary transition-colors",
        "hover:bg-panel-raised hover:text-text-primary",
        className,
      )}
      onClick={() => setOpenSearch(true)}
    >
      <SearchIcon className="size-4 shrink-0" strokeWidth={1.5} />
      <span className="flex-1 text-left">Search…</span>
      <span className="hidden items-center gap-1 md:inline-flex">
        <Kbd>{modifier}</Kbd>
        <Kbd>K</Kbd>
      </span>
    </button>
  );
}
