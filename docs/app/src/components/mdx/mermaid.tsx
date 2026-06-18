"use client";

import dynamic from "next/dynamic";

import { MermaidStaticShell } from "@/components/mdx/mermaid-static-shell";
import { useDiagramChart } from "@/hooks/use-diagram-chart";
import { useStaticDiagram } from "@/hooks/use-static-diagram";
import { cn } from "@/lib/cn";

const MermaidInteractive = dynamic(
  () =>
    import("@/components/mdx/mermaid-interactive").then(
      (mod) => mod.MermaidInteractive,
    ),
  {
    ssr: false,
    loading: () => (
      <div
        aria-hidden
        className="mermaid-diagram my-8 min-h-[12rem] animate-pulse rounded-[4px] border border-border bg-panel"
      />
    ),
  },
);

type MermaidProps = Readonly<{
  id: string;
  caption?: string;
  className?: string;
}>;

function MermaidPlaceholder({ className }: Readonly<{ className?: string }>) {
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

function MermaidChartError({ className }: Readonly<{ className?: string }>) {
  return (
    <figure className={cn("mermaid-diagram my-10 not-prose", className)}>
      <div className="rounded-[4px] border border-danger/40 bg-panel p-4 text-sm text-text-secondary">
        Diagram source is unavailable. Run <code>pnpm build</code> to export diagram
        assets.
      </div>
    </figure>
  );
}

export function Mermaid({ id: diagramKey, caption, className }: MermaidProps) {
  const staticDiagram = useStaticDiagram(diagramKey);
  const chartSource = useDiagramChart(diagramKey, staticDiagram.failed);

  if (staticDiagram.failed) {
    if (chartSource.loading) {
      return <MermaidPlaceholder className={className} />;
    }
    if (!chartSource.chart || chartSource.failed) {
      return <MermaidChartError className={className} />;
    }
    return (
      <MermaidInteractive
        caption={caption}
        chart={chartSource.chart}
        className={className}
        id={diagramKey}
      />
    );
  }

  if (staticDiagram.loading) {
    return <MermaidPlaceholder className={className} />;
  }

  if (staticDiagram.svg) {
    return (
      <figure className={cn("mermaid-diagram my-10 not-prose", className)}>
        <MermaidStaticShell svg={staticDiagram.svg} />
        {caption ? (
          <figcaption className="mt-3 text-center text-sm text-text-secondary">
            {caption}
          </figcaption>
        ) : null}
      </figure>
    );
  }

  return <MermaidChartError className={className} />;
}
