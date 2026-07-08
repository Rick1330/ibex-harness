"use client";

import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/cn";

type FeedbackWidgetProps = Readonly<{
  pageId: string;
}>;

type FeedbackValue = "helpful" | "not-helpful";

export function FeedbackWidget({ pageId }: FeedbackWidgetProps) {
  const [feedback, setFeedback] = useState<FeedbackValue | null>(null);

  const handleFeedback = (type: FeedbackValue) => {
    setFeedback(type);
    try {
      const key = `ibex-docs-feedback:${pageId}`;
      localStorage.setItem(key, type);
    } catch {
      // ignore quota errors
    }
  };

  if (feedback === "helpful") {
    return (
      <div className="mt-10 border-t border-border pt-6">
        <p className="flex items-center gap-2 text-sm font-medium text-success">
          <ThumbsUp className="size-4" strokeWidth={1.5} />
          Thanks for the feedback.
        </p>
      </div>
    );
  }

  return (
    <div className="mt-10 border-t border-border pt-6">
      <p className="mb-3 text-sm font-medium text-text-primary">
        Was this page helpful?
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          className={cn(
            "inline-flex items-center gap-2 rounded-[4px] border border-border px-3 py-2 text-sm text-text-secondary",
            "hover:bg-panel-raised hover:text-text-primary",
          )}
          onClick={() => { handleFeedback("helpful"); }}
          type="button"
        >
          <ThumbsUp className="size-4" strokeWidth={1.5} />
          Yes
        </button>
        <button
          className={cn(
            "inline-flex items-center gap-2 rounded-[4px] border border-border px-3 py-2 text-sm text-text-secondary",
            "hover:bg-panel-raised hover:text-text-primary",
          )}
          onClick={() => { handleFeedback("not-helpful"); }}
          type="button"
        >
          <ThumbsDown className="size-4" strokeWidth={1.5} />
          No
        </button>
      </div>
      {feedback === "not-helpful" ? (
        <p className="mt-3 text-sm text-text-secondary">
          Open an issue on{" "}
          <a
            className="text-text-primary underline decoration-border underline-offset-2 hover:decoration-border-strong"
            href="https://github.com/Rick1330/ibex-harness/issues/new"
            rel="noopener noreferrer"
            target="_blank"
          >
            GitHub
          </a>{" "}
          and tell us what to improve.
        </p>
      ) : null}
    </div>
  );
}
