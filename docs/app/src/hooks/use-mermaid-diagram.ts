"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";

import { hashString } from "@/lib/hash-string";
import {
  cleanStaleMermaidNodes,
  createMermaidRenderId,
  mermaidErrorMessage,
  renderMermaidChart,
} from "@/lib/mermaid-render";

export function useMermaidDiagram(chart: string, stableId?: string) {
  const containerRef = useRef<HTMLDivElement>(null);
  const renderIdRef = useRef("");
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [error, setError] = useState("");
  const [rendering, setRendering] = useState(true);

  const normalizedChart = chart.replaceAll(String.raw`\n`, "\n").trim();
  const chartHash = hashString(normalizedChart);
  const diagramKey = stableId ?? chartHash;
  const isDark = (resolvedTheme ?? "dark") === "dark";

  useEffect(() => {
    setMounted(true);
  }, []);

  const renderDiagram = useCallback(async () => {
    const host = containerRef.current;
    if (!host) return;

    setRendering(true);
    setError("");

    const uniqueId = createMermaidRenderId(diagramKey, chartHash);
    renderIdRef.current = uniqueId;
    cleanStaleMermaidNodes(`mermaid-${diagramKey}`);

    try {
      const isCurrent = () => renderIdRef.current === uniqueId;
      await renderMermaidChart(host, {
        uniqueId,
        normalizedChart,
        isDark,
        isCurrent,
      });
      if (isCurrent()) setRendering(false);
    } catch (err) {
      if (renderIdRef.current !== uniqueId) return;
      setError(mermaidErrorMessage(err));
      setRendering(false);
    }
  }, [chartHash, diagramKey, isDark, normalizedChart]);

  useEffect(() => {
    if (!mounted) return;
    renderDiagram().catch(() => undefined);
  }, [mounted, renderDiagram]);

  return {
    containerRef,
    mounted,
    error,
    rendering,
    chartHash,
    diagramKey,
    isDark,
  };
}
