import { renderMermaidAscii } from "beautiful-mermaid";

/** Normalize MDX mermaid source to a stable chart string. */
export function normalizeMermaidChart(chart: string): string {
  return chart.replaceAll(String.raw`\n`, "\n").trim();
}

export type MermaidAsciiResult = Readonly<{
  ascii: string | null;
  source: string;
}>;

/** Convert Mermaid source to ASCII at build time (no browser / no network). */
export function mermaidToAscii(chart: string): MermaidAsciiResult {
  const source = normalizeMermaidChart(chart);
  if (!source) {
    return { ascii: null, source: "" };
  }

  try {
    const ascii = renderMermaidAscii(source, { useAscii: true });
    if (!ascii.trim()) {
      return { ascii: null, source };
    }
    return { ascii, source };
  } catch {
    return { ascii: null, source };
  }
}
