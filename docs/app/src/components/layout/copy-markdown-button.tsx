"use client";

import { Check, Copy } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { cn } from "@/lib/cn";

const COPY_RESET_MS = 2000;

type CopyMarkdownButtonProps = Readonly<{
  markdownUrl: string;
  className?: string;
}>;

export function CopyMarkdownButton({
  markdownUrl,
  className,
}: CopyMarkdownButtonProps) {
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const timeoutRef = useRef<number | null>(null);
  const cacheRef = useRef<string | null>(null);

  const handleCopy = useCallback(async () => {
    setLoading(true);
    try {
      let markdown = cacheRef.current;
      if (!markdown) {
        const response = await fetch(markdownUrl);
        if (!response.ok) return;
        markdown = await response.text();
        cacheRef.current = markdown;
      }
      await navigator.clipboard.writeText(markdown);
    } catch {
      return;
    } finally {
      setLoading(false);
    }

    if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
    setCopied(true);
    timeoutRef.current = window.setTimeout(() => {
      setCopied(false);
    }, COPY_RESET_MS);
  }, [markdownUrl]);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
    };
  }, []);

  return (
    <button
      type="button"
      aria-label="Copy page content as Markdown"
      disabled={loading}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-[4px] border border-border bg-panel px-3 py-1.5 text-xs font-semibold tracking-wide text-text-secondary transition-all duration-200",
        "hover:bg-panel-raised hover:text-text-primary disabled:opacity-60",
        className,
      )}
      onClick={handleCopy}
    >
      {copied ? (
        <>
          <Check
            aria-hidden
            className="size-3.5 text-emerald-500"
            strokeWidth={2}
          />
          <span className="text-emerald-600 dark:text-emerald-400">Copied!</span>
        </>
      ) : (
        <>
          <Copy aria-hidden className="size-3.5 opacity-80" strokeWidth={2} />
          <span>{loading ? "Loading…" : "Copy Markdown"}</span>
        </>
      )}
    </button>
  );
}
