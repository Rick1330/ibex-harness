/** Normalize MDX / build-script mermaid source to a stable chart string. */
export function normalizeMermaidChart(chart: string): string {
  return chart.replaceAll(String.raw`\n`, "\n").trim();
}
