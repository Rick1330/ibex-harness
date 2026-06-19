"use client";

import dynamic from "next/dynamic";

import {
  MermaidPlaceholder,
} from "@/components/mdx/mermaid-diagram-states";
import { MermaidProduction } from "@/components/mdx/mermaid-production";
import { useDiagramChart } from "@/hooks/use-diagram-chart";
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

function MermaidDevClient({ id: diagramKey, caption, className }: MermaidProps) {
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
      <MermaidDevClient
        caption={caption}
        className={className}
        id={diagramKey}
      />
    );
  }

  return (
    <MermaidProduction
      caption={caption}
      className={className}
      diagramKey={diagramKey}
    />
  );
}
