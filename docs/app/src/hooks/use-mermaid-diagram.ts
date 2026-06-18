"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { useDiagramTheme } from "@/hooks/use-diagram-theme";
import { hashString } from "@/lib/hash-string";
import { normalizeMermaidChart } from "@/lib/normalize-mermaid-chart";
import {
  cleanStaleMermaidNodes,
  createMermaidRenderId,
  mermaidErrorMessage,
  normalizeMountedSvg,
  renderMermaidChart,
} from "@/lib/mermaid-render";

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

    const uniqueId = createMermaidRenderId(diagramKey, chartHash);
    renderIdRef.current = uniqueId;
    setRendering(true);
    setError("");

    cleanStaleMermaidNodes(`mermaid-${diagramKey}`);

    try {
      const isCurrent = () => renderIdRef.current === uniqueId;
      const themedSvg = await renderMermaidChart(host, {
        uniqueId,
        normalizedChart,
        isDark,
        isCurrent,
      });
      if (!isCurrent()) return;
      normalizeMountedSvg(host);
      if (themedSvg) {
        setSvg(themedSvg);
      } else if (!host.querySelector("svg")) {
        throw new Error("Diagram render produced no output");
      }
    } catch (err) {
      if (renderIdRef.current !== uniqueId) return;
      setError(mermaidErrorMessage(err));
    } finally {
      if (renderIdRef.current === uniqueId) {
        setRendering(false);
      }
    }
  }, [chartHash, diagramKey, isDark, normalizedChart]);

  useLayoutEffect(() => {
    if (!mounted || !hostReady) return;
    renderDiagram().catch(() => undefined);
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
