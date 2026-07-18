import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type TerminalCardProps = Readonly<{
  title: string;
  rightMeta?: string;
  children: ReactNode;
  className?: string;
  testId?: string;
}>;

/** Charcoal terminal shell — identical `--shell-*` tokens in light and dark. */
export function TerminalCard({
  title,
  rightMeta,
  children,
  className = "",
  testId = "terminal-card",
}: TerminalCardProps) {
  return (
    <div className={cn("terminal-card", className)} data-testid={testId}>
      <div className="terminal-card-header">
        <span className="code-shell-dot code-shell-dot-close" aria-hidden />
        <span className="code-shell-dot code-shell-dot-min" aria-hidden />
        <span className="code-shell-dot code-shell-dot-max" aria-hidden />
        <span className="code-shell-title ml-0">{title}</span>
        {rightMeta ? (
          <span className="code-shell-tag shrink-0">{rightMeta}</span>
        ) : null}
      </div>
      <div className="terminal-card-body">{children}</div>
    </div>
  );
}

type Tone = "default" | "muted" | "accent" | "success";

const TONE_CLASS: Record<Tone, string> = {
  default: "code-shell-fg",
  muted: "code-shell-comment",
  accent: "code-shell-prompt",
  success: "code-shell-ok",
};

export function TerminalLines({
  lines,
}: Readonly<{
  lines: ReadonlyArray<{ text: string; tone?: Tone }>;
}>) {
  return (
    <pre className="m-0 whitespace-pre-wrap font-mono text-[0.8125rem] leading-[1.65]">
      {lines.map((line, index) => (
        <span
          key={`${line.text}-${index}`}
          className={cn(
            "block min-h-[1.2em]",
            TONE_CLASS[line.tone ?? "default"],
          )}
        >
          {line.text || "\u00A0"}
        </span>
      ))}
    </pre>
  );
}
