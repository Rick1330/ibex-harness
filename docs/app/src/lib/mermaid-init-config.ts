export function getMermaidInitConfig(isDark: boolean) {
  return {
    startOnLoad: false,
    securityLevel: "strict" as const,
    theme: "base" as const,
    themeVariables: isDark
      ? {
          background: "transparent",
          primaryColor: "#21262d",
          primaryTextColor: "#e6edf3",
          lineColor: "#8b949e",
        }
      : {
          background: "transparent",
          primaryColor: "#f6f8fa",
          primaryTextColor: "#1f2328",
          lineColor: "#656d76",
        },
    htmlLabels: false,
    flowchart: {
      curve: "basis" as const,
      padding: 20,
      htmlLabels: false,
      useMaxWidth: true,
    },
    sequence: {
      diagramMarginX: 20,
      diagramMarginY: 20,
      actorMargin: 50,
      useMaxWidth: true,
    },
    fontFamily: "ui-sans-serif, system-ui, sans-serif",
    fontSize: 14,
  };
}
