"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";

import { applyMermaidSvgTheme } from "@/lib/mermaid-svg-theme";
import { hashString } from "@/lib/hash-string";
import { mermaidThemeVariables } from "@/lib/mermaid-theme-vars";
import { cn } from "@/lib/cn";

type MermaidProps = {
  chart: string;
  caption?: string;
  className?: string;
  id?: string;
};

let diagramCounter = 0;

function cleanStaleMermaidNodes(idPrefix: string) {
  document.getElementById(idPrefix)?.remove();
  document
    .querySelectorAll(`[id^="${idPrefix}"]`)
    .forEach((node) => node.remove());
}

export function Mermaid({ chart, caption, className, id: stableId }: MermaidProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const renderIdRef = useRef("");
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [error, setError] = useState("");
  const [rendering, setRendering] = useState(true);

  const normalizedChart = chart.replaceAll("\\n", "\n").trim();
  const chartHash = hashString(normalizedChart);
  const diagramKey = stableId ?? chartHash;
  const isDark = (resolvedTheme ?? "dark") === "dark";

  useEffect(() => {
    setMounted(true);
  }, []);

  const renderDiagram = useCallback(async () => {
    if (!containerRef.current) return;

    const host = containerRef.current;
    setRendering(true);
    setError("");
    host.innerHTML = "";

    diagramCounter += 1;
    const uniqueId = `mermaid-${diagramKey}-${chartHash}-${diagramCounter}`;
    renderIdRef.current = uniqueId;
    cleanStaleMermaidNodes(`mermaid-${diagramKey}`);

    try {
      const mermaid = (await import("mermaid")).default;

      mermaid.initialize({
        startOnLoad: false,
        securityLevel: "loose",
        theme: "base",
        themeVariables: mermaidThemeVariables(isDark),
        htmlLabels: false,
        flowchart: {
          curve: "basis",
          padding: 20,
          htmlLabels: false,
          useMaxWidth: true,
        },
        sequence: {
          diagramMarginX: 20,
          diagramMarginY: 20,
          actorMargin: 50,
          noteMargin: 10,
          messageMargin: 35,
          mirrorActors: false,
          useMaxWidth: true,
        },
        fontFamily: "ui-sans-serif, system-ui, sans-serif",
        fontSize: 14,
      });

      if (renderIdRef.current !== uniqueId) return;

      const result = await mermaid.render(uniqueId, normalizedChart);

      if (renderIdRef.current !== uniqueId) return;

      host.innerHTML = applyMermaidSvgTheme(result.svg, isDark);
      setRendering(false);
    } catch (err) {
      if (renderIdRef.current !== uniqueId) return;

      setError(err instanceof Error ? err.message : "Diagram failed to render");
      setRendering(false);
    }
  }, [chartHash, diagramKey, isDark, normalizedChart]);

  useEffect(() => {
    if (!mounted) return;
    void renderDiagram();
  }, [mounted, renderDiagram]);

  if (!mounted) {
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

  if (error) {
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

  return (
    <figure
      key={`${diagramKey}-${chartHash}-${isDark ? "dark" : "light"}`}
      className={cn("mermaid-diagram my-10 not-prose", className)}
      data-mermaid-key={diagramKey}
      data-mermaid-hash={chartHash}
    >
      <div
        className={cn(
          "mermaid-container relative flex min-h-[200px] items-center justify-center overflow-x-auto rounded-[4px] border border-border bg-[hsl(220_14%_98%)] p-6 dark:bg-[#0d1117]",
        )}
        data-mermaid
      >
        <div
          ref={containerRef}
          className="mermaid w-full max-w-full [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full"
        />
        {rendering ? (
          <div className="absolute inset-0 flex items-center justify-center gap-2 bg-[hsl(220_14%_98%)]/90 text-sm text-text-secondary dark:bg-[#0d1117]/90">
            <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
            Rendering diagram…
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
