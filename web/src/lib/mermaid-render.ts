import { applyMermaidSvgTheme } from "@/lib/mermaid-svg-theme";
import { getMermaidInitConfig } from "@/lib/mermaid-init-config";
import { mermaidThemeVariables } from "@/lib/mermaid-theme-vars";

let diagramCounter = 0;

export function cleanStaleMermaidNodes(idPrefix: string) {
  document.getElementById(idPrefix)?.remove();
  document
    .querySelectorAll(`[id^="${idPrefix}"]`)
    .forEach((node) => node.remove());
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

function mountSvg(host: HTMLDivElement, svg: string) {
  host.replaceChildren();
  try {
    const doc = new DOMParser().parseFromString(svg, "image/svg+xml");
    const root = doc.documentElement;
    if (root?.tagName === "parsererror") {
      throw new Error("Diagram SVG parse failed");
    }
    host.append(root);
  } catch (err) {
    throw err instanceof Error ? err : new Error("Diagram SVG mount failed");
  }
}

export async function renderMermaidChart(
  host: HTMLDivElement,
  options: MermaidRenderOptions,
) {
  const { uniqueId, normalizedChart, isDark, isCurrent } = options;
  host.replaceChildren();

  const mermaid = (await import("mermaid")).default;
  const config = getMermaidInitConfig(isDark);
  mermaid.initialize({
    ...config,
    themeVariables: mermaidThemeVariables(isDark),
  });

  if (!isCurrent()) return null;

  const result = await mermaid.render(uniqueId, normalizedChart);
  if (!isCurrent()) return null;

  mountSvg(host, applyMermaidSvgTheme(result.svg, isDark));
  return result.svg;
}

export function mermaidErrorMessage(err: unknown) {
  return err instanceof Error ? err.message : "Diagram failed to render";
}
