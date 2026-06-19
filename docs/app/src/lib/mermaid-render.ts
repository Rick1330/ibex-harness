import type { MutableRefObject } from "react";

import { applyMermaidSvgTheme } from "@/lib/mermaid-svg-theme";
import { getMermaidInitConfig } from "@/lib/mermaid-init-config";
import { mermaidThemeVariables } from "@/lib/mermaid-theme-vars";

let diagramCounter = 0;

export function cleanStaleMermaidNodes(idPrefix: string) {
  document.querySelectorAll(`[id^="${idPrefix}"]`).forEach((node) => {
    if (node.closest("[data-mermaid]")) return;
    node.remove();
  });
}

export function createMermaidRenderId(diagramKey: string, chartHash: string) {
  diagramCounter += 1;
  return `mermaid-${diagramKey}-${chartHash}-${diagramCounter}`;
}

export type MermaidRenderOptions = {
  uniqueId: string;
  normalizedChart: string;
  isDark: boolean;
  isCurrent: () => boolean;
};

/** Give mounted SVG explicit pixel dimensions from viewBox so flex canvases do not collapse it. */
export function normalizeMountedSvg(host: HTMLDivElement): SVGSVGElement | null {
  const svg = host.querySelector("svg");
  if (!svg) return null;

  const viewBox = svg.viewBox.baseVal;
  const width = viewBox.width > 0 ? viewBox.width : Number.parseFloat(svg.getAttribute("width") ?? "0");
  const height = viewBox.height > 0 ? viewBox.height : Number.parseFloat(svg.getAttribute("height") ?? "0");

  if (width > 0 && height > 0) {
    svg.setAttribute("width", String(width));
    svg.setAttribute("height", String(height));
    svg.style.setProperty("width", `${width}px`, "important");
    svg.style.setProperty("height", `${height}px`, "important");
  }

  svg.style.setProperty("max-width", "none", "important");
  svg.style.setProperty("max-height", "none", "important");
  svg.style.setProperty("display", "block", "important");

  return svg;
}

export function mountSvgString(host: HTMLDivElement, svg: string) {
  host.replaceChildren();
  try {
    const doc = new DOMParser().parseFromString(svg, "image/svg+xml");
    const root = doc.documentElement;
    if (root?.tagName === "parsererror") {
      throw new Error("Diagram SVG parse failed");
    }
    const adopted = document.importNode(root, true);
    host.append(adopted);
    normalizeMountedSvg(host);
  } catch (err) {
    throw err instanceof Error ? err : new Error("Diagram SVG mount failed");
  }
}

export async function renderMermaidChart(
  host: HTMLDivElement,
  options: MermaidRenderOptions,
) {
  const { uniqueId, normalizedChart, isDark, isCurrent } = options;

  const mermaid = (await import("mermaid")).default;
  const config = getMermaidInitConfig(isDark);
  mermaid.initialize({
    ...config,
    themeVariables: mermaidThemeVariables(isDark),
  });

  if (!isCurrent()) return null;

  const result = await mermaid.render(uniqueId, normalizedChart);
  if (!isCurrent()) return null;

  const themedSvg = applyMermaidSvgTheme(result.svg, isDark);
  mountSvgString(host, themedSvg);
  result.bindFunctions?.(host);
  return themedSvg;
}

export function mermaidErrorMessage(err: unknown) {
  return err instanceof Error ? err.message : "Diagram failed to render";
}

type RenderDiagramHostState = Readonly<{
  setRendering: (value: boolean) => void;
  setError: (value: string) => void;
  setSvg: (value: string | null) => void;
}>;

export type RenderDiagramHostOptions = Readonly<{
  host: HTMLDivElement;
  diagramKey: string;
  chartHash: string;
  normalizedChart: string;
  isDark: boolean;
  renderIdRef: MutableRefObject<string>;
  state: RenderDiagramHostState;
}>;

export async function renderDiagramToHost(options: RenderDiagramHostOptions) {
  const {
    host,
    diagramKey,
    chartHash,
    normalizedChart,
    isDark,
    renderIdRef,
    state,
  } = options;

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
