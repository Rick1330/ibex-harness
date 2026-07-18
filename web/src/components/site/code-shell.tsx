"use client";

import { RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";

export type CodeShellLine =
  | { k: "comment"; t: string }
  | { k: "prompt"; t: string }
  | { k: "output"; t: string }
  | { k: "success"; t: string };

type CodeShellProps = Readonly<{
  title?: string;
  tag?: string;
  lines: ReadonlyArray<CodeShellLine>;
  statusRight?: string;
  className?: string;
  testId?: string;
  animate?: boolean;
}>;

/**
 * Code shell (DESIGN_GUIDE.md §11).
 * Charcoal terminal — identical tokens in light and dark.
 * SSR renders all lines; line-reveal starts only after mount.
 */
export function CodeShell({
  title = "~/ibex — zsh",
  tag = "v0.1",
  lines,
  statusRight = "p99 · 18ms",
  className = "",
  testId = "code-shell",
  animate = true,
}: CodeShellProps) {
  const [visible, setVisible] = useState(lines.length);
  const [replayKey, setReplayKey] = useState(0);
  const [runAnimation, setRunAnimation] = useState(false);

  useEffect(() => {
    if (!animate) return;
    if (typeof globalThis.matchMedia === "function") {
      const media = globalThis.matchMedia("(prefers-reduced-motion: reduce)");
      if (media.matches) return;
    }
    setVisible(0);
    setRunAnimation(true);
  }, [animate, lines.length, replayKey]);

  useEffect(() => {
    if (!runAnimation) return;
    const id = globalThis.setInterval(() => {
      setVisible((current) => {
        if (current >= lines.length) {
          globalThis.clearInterval(id);
          return current;
        }
        return current + 1;
      });
    }, 90);
    return () => globalThis.clearInterval(id);
  }, [runAnimation, lines.length, replayKey]);

  const shown = lines.slice(0, visible);

  return (
    <div className={cn("code-shell", className)} data-testid={testId}>
      <div className="code-shell-header">
        <span className="code-shell-dot code-shell-dot-close" aria-hidden />
        <span className="code-shell-dot code-shell-dot-min" aria-hidden />
        <span className="code-shell-dot code-shell-dot-max" aria-hidden />
        <span className="code-shell-title">{title}</span>
        <span className="code-shell-tag">{tag}</span>
      </div>

      <pre className="code-shell-body">
        {shown.map((line, index) => (
          <div
            key={`${line.k}-${line.t}-${index}`}
            className="code-shell-line"
          >
            {line.k === "comment" ? (
              <span className="code-shell-comment"># {line.t}</span>
            ) : null}
            {line.k === "prompt" ? (
              <>
                <span className="code-shell-prompt">$ </span>
                <span className="code-shell-fg">{line.t}</span>
              </>
            ) : null}
            {line.k === "output" ? (
              <span className="code-shell-fg">{line.t || "\u00A0"}</span>
            ) : null}
            {line.k === "success" ? (
              <span className="code-shell-ok">{line.t}</span>
            ) : null}
          </div>
        ))}
        {runAnimation && visible < lines.length ? (
          <span className="caret code-shell-fg" aria-hidden />
        ) : null}
      </pre>

      <div className="code-shell-status">
        <span>{statusRight}</span>
        <button
          type="button"
          className="code-shell-replay"
          onClick={() => {
            setRunAnimation(false);
            setReplayKey((key) => key + 1);
          }}
          aria-label="Replay shell animation"
        >
          <RotateCcw className="size-3" aria-hidden />
          replay
        </button>
      </div>
    </div>
  );
}
