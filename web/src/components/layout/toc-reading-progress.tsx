"use client";

import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";

type TocReadingProgressProps = Readonly<{
  className?: string;
}>;

export function useReadingProgress() {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const onScroll = () => {
      const element = document.scrollingElement;
      if (!element) return;

      const { scrollTop, scrollHeight, clientHeight } = element;
      const range = scrollHeight - clientHeight;
      setProgress(range > 0 ? (scrollTop / range) * 100 : 0);
    };

    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
    };
  }, []);

  return progress;
}

export function TocReadingProgress({ className }: TocReadingProgressProps) {
  const progress = useReadingProgress();
  const pct = Math.round(progress);

  return (
    <div className={cn("border-t border-border pt-3", className)}>
      <div className="flex items-center gap-2">
        <progress
          aria-label="Reading progress"
          className="toc-reading-progress h-1 min-w-0 flex-1"
          max={100}
          value={pct}
        />
        <span className="shrink-0 font-mono text-xs tabular-nums text-text-tertiary">
          {pct}%
        </span>
      </div>
    </div>
  );
}
