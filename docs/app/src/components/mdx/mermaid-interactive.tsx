"use client";

import { cn } from "@/lib/cn";
import { useMermaidDiagram } from "@/hooks/use-mermaid-diagram";
import { DeepWikiStyleWrapper } from "@/components/mdx/interactive-mermaid";

export type MermaidInteractiveProps = Readonly<{
  chart: string;
  caption?: string;
  className?: string;
  id?: string;
  onCollapse?: () => void;
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

export function MermaidInteractive({
  chart,
  caption,
  className,
  id: stableId,
  onCollapse,
}: MermaidInteractiveProps) {
  const {
    containerRef,
    hostRef,
    mounted,
    error,
    rendering,
    svg,
    chartHash,
    diagramKey,
  } = useMermaidDiagram(chart, stableId);

  if (!mounted) return <MermaidPlaceholder className={className} />;
  if (error) return <MermaidError error={error} className={className} />;

  return (
    <figure
      className={cn("mermaid-diagram my-10 not-prose", className)}
      data-mermaid-key={diagramKey}
      data-mermaid-hash={chartHash}
    >
      <DeepWikiStyleWrapper
        hostRef={hostRef}
        onCollapse={onCollapse}
        rendering={rendering}
        svg={svg}
      >
        <div
          className="mermaid-container relative min-h-[8rem] min-w-[12rem] rounded-[4px] border border-border/60 bg-panel p-4"
          data-mermaid
        >
          <div ref={containerRef} className="mermaid leading-none" />
          {rendering ? (
            <div className="absolute inset-0 flex items-center justify-center gap-2 bg-panel/90 text-sm text-text-secondary">
              <span
                aria-hidden
                className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent"
              />
              <span>Rendering diagram…</span>
            </div>
          ) : null}
        </div>
      </DeepWikiStyleWrapper>
      {caption ? (
        <figcaption className="mt-3 text-center text-sm text-text-secondary">
          {caption}
        </figcaption>
      ) : null}
    </figure>
  );
}
