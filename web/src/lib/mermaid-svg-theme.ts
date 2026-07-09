/** Post-process Mermaid SVG for readable native text labels (htmlLabels: false). */
export function applyMermaidSvgTheme(svg: string, isDark: boolean): string {
  const text = isDark ? "#e6edf3" : "#1f2328";
  const nodeFill = isDark ? "#21262d" : "#f6f8fa";
  const nodeStroke = isDark ? "#30363d" : "#d0d7de";
  const line = isDark ? "#8b949e" : "#656d76";
  const edgeLabelBg = isDark ? "#21262d" : "#ffffff";
  const edgeLabelText = isDark ? "#c9d1d9" : "#57606a";
  const clusterFill = isDark ? "#161b22" : "#eef2f6";

  const css = `
    .node rect, .node circle, .node polygon, .node path:not(.flowchart-link) {
      fill: ${nodeFill} !important;
      stroke: ${nodeStroke} !important;
    }
    .cluster rect {
      fill: ${clusterFill} !important;
      stroke: ${nodeStroke} !important;
    }
    .edgePath path, .flowchart-link, .edgePaths path {
      stroke: ${line} !important;
    }
    marker path {
      fill: ${line} !important;
      stroke: ${line} !important;
    }
    text, tspan, .label, .nodeLabel, .edgeLabel {
      fill: ${text} !important;
    }
    .edgeLabel rect {
      fill: ${edgeLabelBg} !important;
      stroke: ${nodeStroke} !important;
    }
    .edgeLabel text, .edgeLabel tspan {
      fill: ${edgeLabelText} !important;
    }
  `.trim();

  let result = svg.replace(
    /<svg([^>]*)>/i,
    `<svg$1><style type="text/css">${css}</style>`,
  );

  result = result.replace(/<text\b([^>]*?)>/gi, (full, attrs) => {
    const cleaned = String(attrs).replace(/\sfill="[^"]*"/gi, "");
    return `<text${cleaned} fill="${text}">`;
  });

  result = result.replace(/<tspan\b([^>]*?)>/gi, (full, attrs) => {
    const cleaned = String(attrs).replace(/\sfill="[^"]*"/gi, "");
    return `<tspan${cleaned} fill="${text}">`;
  });

  return result;
}
