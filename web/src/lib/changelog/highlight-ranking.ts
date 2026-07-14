import type { ChangeItem } from "./types";

const HIGHLIGHT_CAP = 5;
const DOCS_HIGHLIGHT_CAP = 2;

const INTERNAL_SCOPES = new Set(["ci", "test", "dx", "docker"]);
const USER_FACING_SCOPES = new Set([
  "auth",
  "proxy",
  "db",
  "web",
  "bench",
  "infra",
  "docs",
]);

type CapState = {
  internalCounts: Map<string, number>;
  docsCount: number;
};

function scoreHighlight(item: ChangeItem): number {
  let score = 0;
  if (item.issueNumber !== null) score += 10;
  if (item.scope && USER_FACING_SCOPES.has(item.scope)) score += 5;
  if (item.priority === "internal") score -= 8;
  if (item.scope === "docs") score -= 2;
  return score;
}

function shouldSkipForCaps(item: ChangeItem, caps: CapState): boolean {
  if (item.priority === "internal" && item.scope) {
    if ((caps.internalCounts.get(item.scope) ?? 0) >= 1) return true;
  }
  return item.scope === "docs" && caps.docsCount >= DOCS_HIGHLIGHT_CAP;
}

function recordCapUsage(item: ChangeItem, caps: CapState): void {
  if (item.priority === "internal" && item.scope) {
    caps.internalCounts.set(
      item.scope,
      (caps.internalCounts.get(item.scope) ?? 0) + 1,
    );
  }
  if (item.scope === "docs") caps.docsCount += 1;
}

/** Ranks section items and returns up to five curated highlights. */
export function selectHighlights(items: ChangeItem[]): ChangeItem[] {
  if (items.length === 0) return [];

  const ranked = [...items].sort(
    (a, b) => scoreHighlight(b) - scoreHighlight(a),
  );
  const highlights: ChangeItem[] = [];
  const caps: CapState = { internalCounts: new Map(), docsCount: 0 };

  for (const item of ranked) {
    if (highlights.length >= HIGHLIGHT_CAP) break;
    if (shouldSkipForCaps(item, caps)) continue;
    recordCapUsage(item, caps);
    highlights.push({ ...item, priority: "highlight" });
  }

  return highlights;
}

export function classifyChangePriority(
  scope: string | null,
): ChangeItem["priority"] {
  if (scope && INTERNAL_SCOPES.has(scope)) return "internal";
  return "standard";
}
