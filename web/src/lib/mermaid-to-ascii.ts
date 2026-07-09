import { renderMermaidAscii } from "beautiful-mermaid";

const ANSI_SEQUENCE_RE = /\x1B\[[0-9;]*m/g;

/** Normalize MDX mermaid source to a stable chart string. */
export function normalizeMermaidChart(chart: string): string {
  return chart.replaceAll(String.raw`\n`, "\n").trim();
}

/** Strip terminal color codes so ASCII renders cleanly in the browser. */
export function stripAnsiSequences(text: string): string {
  return text.replace(ANSI_SEQUENCE_RE, "");
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
    const raw = renderMermaidAscii(source, {
      useAscii: true,
      colorMode: "none",
    });
    const ascii = stripAnsiSequences(raw);
    if (!ascii.trim()) {
      return { ascii: null, source };
    }
    return { ascii, source };
  } catch {
    return { ascii: null, source };
  }
}
