function buildThemeCss(isDark: boolean): string {
  const text = isDark ? "#e6edf3" : "#1f2328";
  const nodeFill = isDark ? "#21262d" : "#f6f8fa";
  const nodeStroke = isDark ? "#30363d" : "#d0d7de";
  const line = isDark ? "#8b949e" : "#656d76";
  const edgeLabelBg = isDark ? "#21262d" : "#ffffff";
  const edgeLabelText = isDark ? "#c9d1d9" : "#57606a";
  const clusterFill = isDark ? "#161b22" : "#eef2f6";

  return `
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
    marker path, #arrowhead path {
      fill: ${line} !important;
      stroke: ${line} !important;
    }
    text, tspan, .label, .nodeLabel, .edgeLabel, .entityLabel, .relationshipLabel {
      fill: ${text} !important;
    }
    .edgeLabel rect {
      fill: ${edgeLabelBg} !important;
      stroke: ${nodeStroke} !important;
    }
    .edgeLabel text, .edgeLabel tspan {
      fill: ${edgeLabelText} !important;
    }
    .actor, .actor-line, .messageLine0, .messageLine1 {
      stroke: ${line} !important;
    }
    .actor rect, .actor path, .entityBox, .attributeBoxOdd, .attributeBoxEven {
      fill: ${nodeFill} !important;
      stroke: ${nodeStroke} !important;
    }
    .messageText0, .messageText1, .loopText, .loopText tspan {
      fill: ${text} !important;
    }
    .relationshipLine {
      stroke: ${line} !important;
    }
    foreignObject div, foreignObject span, foreignObject p {
      color: ${text} !important;
    }
    foreignObject .labelBkg, .labelBkg {
      background-color: ${edgeLabelBg} !important;
    }
  `.trim();
}

/** Post-process Mermaid SVG for readable native text labels (htmlLabels: false). */
export function applyMermaidSvgTheme(svg: string, isDark: boolean): string {
  const text = isDark ? "#e6edf3" : "#1f2328";
  const css = buildThemeCss(isDark);

  let result = svg.replace(
    /<svg([^>]*)>/i,
    `<svg$1><style type="text/css">${css}</style>`,
  );

  result = result.replace(/<text\b([^>]*?)>/gi, (_full, attrs) => {
    const cleaned = String(attrs).replace(/\sfill="[^"]*"/gi, "");
    return `<text${cleaned} fill="${text}">`;
  });

  result = result.replace(/<tspan\b([^>]*?)>/gi, (_full, attrs) => {
    const cleaned = String(attrs).replace(/\sfill="[^"]*"/gi, "");
    return `<tspan${cleaned} fill="${text}">`;
  });

  return result;
}
