"use client";

import { useEffect, useState } from "react";

/** 2px accent reading progress — DESIGN_GUIDE §14.2. */
export function ReadingProgress() {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const onScroll = () => {
      const el = document.documentElement;
      const max = el.scrollHeight - el.clientHeight;
      if (max <= 0) {
        setProgress(0);
        return;
      }
      setProgress(Math.min(100, Math.max(0, (el.scrollTop / max) * 100)));
    };

    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
    };
  }, []);

  return (
    <progress
      className="blog-reading-progress"
      max={100}
      value={progress}
      aria-label="Reading progress"
    />
  );
}
