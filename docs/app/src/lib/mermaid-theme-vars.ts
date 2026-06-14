export const DARK_THEME_VARS = {
  background: "transparent",
  primaryColor: "#21262d",
  primaryTextColor: "#e6edf3",
  primaryBorderColor: "#30363d",
  lineColor: "#8b949e",
  secondaryColor: "#161b22",
  tertiaryColor: "#0d1117",
  edgeLabelBackground: "#21262d",
  clusterBkg: "#161b22",
  clusterBorder: "#30363d",
  titleColor: "#e6edf3",
  nodeTextColor: "#e6edf3",
  textColor: "#e6edf3",
  mainBkg: "#21262d",
  noteTextColor: "#c9d1d9",
  noteBorderColor: "#30363d",
  actorTextColor: "#e6edf3",
  labelTextColor: "#c9d1d9",
};

export const LIGHT_THEME_VARS = {
  background: "transparent",
  primaryColor: "#f6f8fa",
  primaryTextColor: "#1f2328",
  primaryBorderColor: "#d0d7de",
  lineColor: "#656d76",
  secondaryColor: "#eef2f6",
  tertiaryColor: "#ffffff",
  edgeLabelBackground: "#ffffff",
  clusterBkg: "#eef2f6",
  clusterBorder: "#d0d7de",
  titleColor: "#1f2328",
  nodeTextColor: "#1f2328",
  textColor: "#1f2328",
  mainBkg: "#f6f8fa",
  noteTextColor: "#57606a",
  noteBorderColor: "#d0d7de",
  actorTextColor: "#1f2328",
  labelTextColor: "#57606a",
};

export function mermaidThemeVariables(isDark: boolean) {
  return isDark ? DARK_THEME_VARS : LIGHT_THEME_VARS;
}
