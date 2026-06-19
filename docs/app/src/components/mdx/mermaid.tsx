"use client";

import dynamic from "next/dynamic";

import { MermaidStaticShell } from "@/components/mdx/mermaid-static-shell";
import { useDiagramChart } from "@/hooks/use-diagram-chart";
import { useStaticDiagram } from "@/hooks/use-static-diagram";
import { cn } from "@/lib/cn";

const isDev = process.env.NODE_ENV === "development";

const MermaidInline = dynamic(
  () =>
    import("@/components/mdx/mermaid-inline").then((mod) => mod.MermaidInline),
  {
    ssr: false,
    loading: () => <MermaidPlaceholder />,
  },
);

type MermaidProps = Readonly<{
  id: string;
  caption?: string;
  className?: string;
}>;

function MermaidPlaceholder({ className }: Readonly<{ className?: string }> = {}) {
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

function MermaidClientFallback({
  diagramKey,
  caption,
  className,
}: Readonly<{
  diagramKey: string;
  caption?: string;
  className?: string;
}>) {
  const chartSource = useDiagramChart(diagramKey, true);

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

export function Mermaid({ id: diagramKey, caption, className }: MermaidProps) {
  if (isDev) {
    return (
      <MermaidClientFallback
        caption={caption}
        className={className}
        diagramKey={diagramKey}
      />
    );
  }

  const staticDiagram = useStaticDiagram(diagramKey, { enabled: true });
  const chartSource = useDiagramChart(
    diagramKey,
    staticDiagram.failed || staticDiagram.loading,
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
