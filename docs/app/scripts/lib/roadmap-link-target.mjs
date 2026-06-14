import path from "node:path";

const FILE_RENAMES = new Map([
  ["PHASE1_EXIT_AUDIT.md", "phase1-exit-audit"],
  ["TEST_ARCHITECTURE.md", "test-architecture"],
  ["CI_AUDIT.md", "ci-audit"],
  ["MASTER_BRIEF.md", "master-brief"],
  ["CONTENT_SOURCES.md", "content-sources"],
  ["1.2.6-and-1.2.7-reqid-and-shutdown.md", "1.2.6-request-id-correlation-middleware"],
]);

const SPECIAL_HREFS = new Map([
  ["CURRENT_STATE.md", "/roadmap/current-state"],
  ["FINDINGS.md", "/roadmap/findings"],
  ["PHASES.md", "/roadmap/overview"],
  ["../CURRENT_STATE.md", "/roadmap/current-state"],
  ["../FINDINGS.md", "/roadmap/findings"],
  ["../PHASES.md", "/roadmap/overview"],
  ["../../CURRENT_STATE.md", "/roadmap/current-state"],
  ["../../FINDINGS.md", "/roadmap/findings"],
]);

function isPassthroughHref(normalized) {
  return (
    normalized.startsWith("http") ||
    normalized.startsWith("/") ||
    normalized.startsWith("#")
  );
}

function joinRelativePath(rel, fileDir) {
  const parts = fileDir.split("/").filter(Boolean);
  for (const seg of rel.split("/")) {
    if (seg === "..") parts.pop();
    else if (seg !== ".") parts.push(seg);
  }
  return parts.join("/");
}

function normalizeRelativePath(normalized, fileDir) {
  let rel = normalized.startsWith("./") ? normalized.slice(2) : normalized;
  if (rel.startsWith("../")) return joinRelativePath(rel, fileDir);
  if (rel.startsWith("phase-")) return rel;
  return `${fileDir}/${rel}`.replace(/\/+/g, "/");
}

function stripMarkdownExtension(rel, fileDir) {
  const base = path.basename(rel);
  if (FILE_RENAMES.has(base)) return rel.replace(base, FILE_RENAMES.get(base));
  if (base === "README.md") {
    const stripped = rel.replace(/\/README\.md$/, "").replace(/README\.md$/, "");
    return stripped || fileDir;
  }
  if (base.endsWith(".md")) return rel.slice(0, -3);
  return rel;
}

function toRoadmapUrl(rel) {
  const cleaned = rel.replace(/\\/g, "/").replace(/\/index$/, "");
  return `/roadmap/${cleaned.replace(/^\/+/, "")}`;
}

export function resolveRoadmapLinkTarget(href, fileDir, tryAdrHref) {
  const normalized = href.replace(/\\/g, "/");
  if (isPassthroughHref(normalized)) return href;

  const adr = tryAdrHref?.(normalized);
  if (adr) return adr;

  if (SPECIAL_HREFS.has(normalized)) return SPECIAL_HREFS.get(normalized);

  const rel = stripMarkdownExtension(
    normalizeRelativePath(normalized, fileDir),
    fileDir,
  );
  return toRoadmapUrl(rel);
}

export function isAdrPath(pathPart) {
  const base = path.basename(pathPart.replaceAll("\\", "/"));
  return pathPart.includes("/adr/") || base.toUpperCase().startsWith("ADR-");
}
