export type DiagramTheme = "light" | "dark";

export function getStaticDiagramUrl(
  diagramKey: string,
  theme: DiagramTheme,
): string {
  return `/diagrams/${diagramKey}-${theme}.svg`;
}

export function getDiagramChartUrl(diagramKey: string): string {
  return `/diagrams/${diagramKey}.mmd`;
}
