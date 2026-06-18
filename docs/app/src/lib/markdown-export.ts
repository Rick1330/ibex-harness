export type MarkdownExportSection = "docs" | "roadmap" | "blog";

/** Stable URL-safe id for a content file within a section. */
export function getMarkdownExportId(
  section: MarkdownExportSection,
  filePath: string,
): string {
  const normalized = filePath.replaceAll("\\", "/");
  const key = `${section}/${normalized}`;
  return Buffer.from(key, "utf8").toString("base64url");
}

/** Public URL for pre-exported page markdown (generated at build). */
export function getMarkdownExportUrl(
  section: MarkdownExportSection,
  filePath: string,
): string {
  return `/markdown/${getMarkdownExportId(section, filePath)}.md`;
}
