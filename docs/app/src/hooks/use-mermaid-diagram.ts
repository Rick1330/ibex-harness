"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { useDiagramTheme } from "@/hooks/use-diagram-theme";
import { hashString } from "@/lib/hash-string";
import { normalizeMermaidChart } from "@/lib/normalize-mermaid-chart";
import { renderDiagramToHost } from "@/lib/mermaid-render";

function ignoreCancelledRender() {
  // Layout effect may re-run before an in-flight render completes.
}

export function useMermaidDiagram(chart: string, stableId?: string) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const renderIdRef = useRef("");
  const diagramTheme = useDiagramTheme();
  const [mounted, setMounted] = useState(false);
  const [hostReady, setHostReady] = useState(false);
  const [error, setError] = useState("");
  const [rendering, setRendering] = useState(true);
  const [svg, setSvg] = useState<string | null>(null);

  const normalizedChart = normalizeMermaidChart(chart);
  const chartHash = hashString(normalizedChart);
  const diagramKey = stableId ?? `diagram-${chartHash}`;
  const isDark = diagramTheme === "dark";

  const setContainerRef = useCallback((node: HTMLDivElement | null) => {
    hostRef.current = node;
    setHostReady(node !== null);
  }, []);

  useEffect(() => {
    setMounted(true);
  }, []);

  const renderDiagram = useCallback(async () => {
    const host = hostRef.current;
    if (!host) return;
    await renderDiagramToHost({
      host,
      diagramKey,
      chartHash,
      normalizedChart,
      isDark,
      renderIdRef,
      state: { setRendering, setError, setSvg },
    });
  }, [chartHash, diagramKey, isDark, normalizedChart]);

  useLayoutEffect(() => {
    if (!mounted || !hostReady) return;
    renderDiagram().catch(ignoreCancelledRender);
  }, [hostReady, mounted, renderDiagram]);

  return {
    containerRef: setContainerRef,
    hostRef,
    mounted,
    error,
    rendering,
    svg,
    chartHash,
    diagramKey,
    isDark,
  };
}
