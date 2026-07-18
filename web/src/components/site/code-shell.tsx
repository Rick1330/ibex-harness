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

function prefersReducedMotion(): boolean {
  if (typeof globalThis.matchMedia !== "function") return false;
  return globalThis.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function useLineReveal(
  animate: boolean,
  lineCount: number,
  replayKey: number,
): { visible: number; runAnimation: boolean } {
  const [visible, setVisible] = useState(() => (animate ? 0 : lineCount));
  const [runAnimation, setRunAnimation] = useState(false);

  useEffect(() => {
    if (!animate || prefersReducedMotion()) {
      setVisible(lineCount);
      setRunAnimation(false);
      return;
    }
    setVisible(0);
    setRunAnimation(true);
  }, [animate, lineCount, replayKey]);

  useEffect(() => {
    if (!runAnimation) return;
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    const tick = () => {
      setVisible((current) => {
        if (current >= lineCount) return current;
        const next = current + 1;
        if (next < lineCount && !cancelled) {
          timeoutId = setTimeout(tick, 90);
        }
        return next;
      });
    };

    timeoutId = setTimeout(tick, 90);
    return () => {
      cancelled = true;
      if (timeoutId !== undefined) clearTimeout(timeoutId);
    };
  }, [runAnimation, lineCount, replayKey]);

  return { visible, runAnimation };
}

function ShellLine({ line }: Readonly<{ line: CodeShellLine }>) {
  if (line.k === "comment") {
    return <span className="code-shell-comment"># {line.t}</span>;
  }
  if (line.k === "prompt") {
    return (
      <>
        <span className="code-shell-prompt">$ </span>
        <span className="code-shell-fg">{line.t}</span>
      </>
    );
  }
  if (line.k === "success") {
    return <span className="code-shell-ok">{line.t}</span>;
  }
  return <span className="code-shell-fg">{line.t || "\u00A0"}</span>;
}

/**
 * Code shell (DESIGN_GUIDE.md §11).
 * Charcoal terminal — identical tokens in light and dark.
 * SSR renders all lines; line-reveal starts only after mount when animate.
 */
export function CodeShell({
  title = "~/ibex — zsh",
  tag = "v0.1",
  lines,
  statusRight = "p99 · 18ms",
  className = "",
  testId = "code-shell",
  animate = false,
}: CodeShellProps) {
  const [replayKey, setReplayKey] = useState(0);
  const { visible, runAnimation } = useLineReveal(
    animate,
    lines.length,
    replayKey,
  );
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
            <ShellLine line={line} />
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
