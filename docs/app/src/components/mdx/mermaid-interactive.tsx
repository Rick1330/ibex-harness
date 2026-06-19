"use client";

import { cn } from "@/lib/cn";
import {
  MermaidError,
  MermaidPlaceholder,
} from "@/components/mdx/mermaid-diagram-states";
import { DeepWikiStyleWrapper } from "@/components/mdx/interactive-mermaid";
import { useMermaidDiagram } from "@/hooks/use-mermaid-diagram";

export type MermaidInteractiveProps = Readonly<{
  chart: string;
  caption?: string;
  className?: string;
  id?: string;
  onCollapse?: () => void;
}>;

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
            <div className="absolute inset-0 flex items-center justify-center bg-panel/90 text-sm text-text-secondary">
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
