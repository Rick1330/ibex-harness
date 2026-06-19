"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type MutableRefObject } from "react";

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

type RenderState = Readonly<{
  setRendering: (value: boolean) => void;
  setError: (value: string) => void;
  setSvg: (value: string | null) => void;
}>;

async function renderDiagramToHost(
  host: HTMLDivElement,
  diagramKey: string,
  chartHash: string,
  normalizedChart: string,
  isDark: boolean,
  renderIdRef: MutableRefObject<string>,
  state: RenderState,
) {
  const uniqueId = createMermaidRenderId(diagramKey, chartHash);
  renderIdRef.current = uniqueId;
  state.setRendering(true);
  state.setError("");

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
      state.setSvg(themedSvg);
      return;
    }
    if (!host.querySelector("svg")) {
      throw new Error("Diagram render produced no output");
    }
  } catch (err) {
    if (renderIdRef.current !== uniqueId) return;
    state.setError(mermaidErrorMessage(err));
  } finally {
    if (renderIdRef.current === uniqueId) {
      state.setRendering(false);
    }
  }
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
    await renderDiagramToHost(
      host,
      diagramKey,
      chartHash,
      normalizedChart,
      isDark,
      renderIdRef,
      { setRendering, setError, setSvg },
    );
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
