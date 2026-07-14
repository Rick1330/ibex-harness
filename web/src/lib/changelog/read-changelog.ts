import fs from "node:fs";
import path from "node:path";

import { parseChangelogContent } from "./parse-changelog";
import type { ReleaseEntry } from "./types";

const REPO_ROOT = path.resolve(process.cwd(), "..");
const DEFAULT_CHANGELOG = path.join(REPO_ROOT, "CHANGELOG.md");

function assertReadableChangelogPath(candidate: string): string {
  const resolved = path.resolve(candidate);
  const relative = path.relative(REPO_ROOT, resolved);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("changelog path must stay within the repository root");
  }
  if (path.basename(resolved) !== "CHANGELOG.md") {
    throw new Error("changelog path must target CHANGELOG.md");
  }
  return resolved;
}

/** Server-only: reads root CHANGELOG.md at build time. Do not import from client components. */
export function readReleasesFromChangelog(
  changelogPath?: string,
): ReleaseEntry[] {
  const resolved = assertReadableChangelogPath(changelogPath ?? DEFAULT_CHANGELOG);
  const content = fs.readFileSync(resolved, "utf8");
  return parseChangelogContent(content);
}
