"use client";

import { cn } from "@/lib/cn";
import { useMermaidDiagram } from "@/hooks/use-mermaid-diagram";

export type MermaidInlineProps = Readonly<{
  chart: string;
  caption?: string;
  className?: string;
  id?: string;
}>;

type MermaidPlaceholderProps = Readonly<{ className?: string }>;

function MermaidPlaceholder({ className }: MermaidPlaceholderProps) {
  return (
    <div
      aria-hidden
      className={cn(
        "mermaid-diagram my-8 min-h-[12rem] rounded-[4px] border border-border bg-panel",
        className,
      )}
    />
  );
}

type MermaidErrorProps = Readonly<{ error: string; className?: string }>;

function MermaidError({ error, className }: MermaidErrorProps) {
  return (
    <figure className={cn("mermaid-diagram my-10 not-prose", className)}>
      <div className="rounded-[4px] border border-danger/40 bg-panel p-4">
        <p className="mb-1 text-sm font-semibold text-danger">Diagram error</p>
        <pre className="whitespace-pre-wrap font-mono text-xs text-text-secondary">
          {error}
        </pre>
      </div>
    </figure>
  );
}

/** Client-side Mermaid render — full-width inline SVG (main-branch style). */
export function MermaidInline({
  chart,
  caption,
  className,
  id: stableId,
}: MermaidInlineProps) {
  const {
    containerRef,
    mounted,
    error,
    rendering,
    chartHash,
    diagramKey,
    isDark,
  } = useMermaidDiagram(chart, stableId);

  if (!mounted) return <MermaidPlaceholder className={className} />;
  if (error) return <MermaidError error={error} className={className} />;

  return (
    <figure
      key={`${diagramKey}-${chartHash}-${isDark ? "dark" : "light"}`}
      className={cn("mermaid-diagram my-10 not-prose", className)}
      data-mermaid-key={diagramKey}
      data-mermaid-hash={chartHash}
    >
      <div
        className="mermaid-container relative flex min-h-[200px] items-center justify-center overflow-x-auto rounded-[4px] border border-border bg-panel p-6"
        data-mermaid
      >
        <div
          ref={containerRef}
          className="mermaid w-full max-w-full [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full"
        />
        {rendering ? (
          <div className="absolute inset-0 flex items-center justify-center bg-panel/90 text-sm text-text-secondary">
            <span>Rendering diagram…</span>
          </div>
        ) : null}
      </div>
      {caption ? (
        <figcaption className="mt-3 text-center text-sm text-text-secondary">
          {caption}
        </figcaption>
      ) : null}
    </figure>
  );
}
