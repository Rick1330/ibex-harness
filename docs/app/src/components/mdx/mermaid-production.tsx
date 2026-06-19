"use client";

import dynamic from "next/dynamic";

import { MermaidStaticShell } from "@/components/mdx/mermaid-static-shell";
import {
  MermaidPlaceholder,
} from "@/components/mdx/mermaid-diagram-states";
import { useDiagramChart } from "@/hooks/use-diagram-chart";
import { useStaticDiagram } from "@/hooks/use-static-diagram";
import { cn } from "@/lib/cn";

const MermaidInline = dynamic(
  () =>
    import("@/components/mdx/mermaid-inline").then((mod) => mod.MermaidInline),
  {
    ssr: false,
    loading: () => <MermaidPlaceholder />,
  },
);

type MermaidChartBodyProps = Readonly<{
  diagramKey: string;
  caption?: string;
  className?: string;
}>;

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

function MermaidStaticFigure({
  svg,
  caption,
  className,
}: Readonly<{ svg: string; caption?: string; className?: string }>) {
  return (
    <figure className={cn("mermaid-diagram my-10 not-prose", className)}>
      <MermaidStaticShell svg={svg} />
      {caption ? (
        <figcaption className="mt-3 text-center text-sm text-text-secondary">
          {caption}
        </figcaption>
      ) : null}
    </figure>
  );
}

export function MermaidProduction({
  diagramKey,
  caption,
  className,
}: MermaidChartBodyProps) {
  const staticDiagram = useStaticDiagram(diagramKey, { enabled: true });
  const chartSource = useDiagramChart(
    diagramKey,
    staticDiagram.loading || staticDiagram.failed,
  );

  if (staticDiagram.failed) {
    if (chartSource.loading) {
      return <MermaidPlaceholder className={className} />;
    }
    if (!chartSource.chart || chartSource.failed) {
      return <MermaidChartError className={className} />;
    }
    return (
      <MermaidInline
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
      <MermaidStaticFigure
        caption={caption}
        className={className}
        svg={staticDiagram.svg}
      />
    );
  }

  return <MermaidChartError className={className} />;
}
