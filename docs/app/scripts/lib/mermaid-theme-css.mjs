import themeTokens from "../../src/lib/mermaid-theme-tokens.json" with { type: "json" };

function palette(isDark) {
  return isDark ? themeTokens.dark : themeTokens.light;
}

export function buildMermaidThemeCss(isDark) {
  const {
    text,
    nodeFill,
    nodeStroke,
    line,
    edgeLabelBg,
    edgeLabelText,
    clusterFill,
  } = palette(isDark);

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
export function applyMermaidSvgTheme(svg, isDark) {
  const { text } = palette(isDark);
  const css = buildMermaidThemeCss(isDark);

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
