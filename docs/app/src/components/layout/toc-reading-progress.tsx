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
    return () => { window.removeEventListener("scroll", onScroll); };
  }, []);

  return progress;
}

export function TocReadingProgress({ className }: TocReadingProgressProps) {
  const progress = useReadingProgress();

  return (
    <div className={cn("border-t border-border pt-3", className)}>
      <div className="flex items-center gap-2">
        <div
          aria-hidden
          className="h-1 min-w-0 flex-1 overflow-hidden rounded-[4px] bg-panel-raised"
        >
          <div
            className="h-full bg-accent transition-[width] duration-150 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
        <span className="shrink-0 font-mono text-xs tabular-nums text-text-tertiary">
          {Math.round(progress)}%
        </span>
      </div>
    </div>
  );
}
