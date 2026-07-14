import fs from "node:fs";
import path from "node:path";

import { parseChangelogContent } from "./parse-changelog";
import type { ReleaseEntry } from "./types";

const REPO_ROOT = path.resolve(process.cwd(), "..");
const CHANGELOG_FILE = path.join(REPO_ROOT, "CHANGELOG.md");

function assertReadableChangelogPath(): string {
  if (path.basename(CHANGELOG_FILE) !== "CHANGELOG.md") {
    throw new Error("changelog path must target CHANGELOG.md");
  }

  let canonical: string;
  try {
    canonical = fs.realpathSync(CHANGELOG_FILE);
  } catch {
    throw new Error("changelog path is not readable");
  }

  const repoRoot = fs.realpathSync(REPO_ROOT);
  const relative = path.relative(repoRoot, canonical);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("changelog path must stay within the repository root");
  }

  return canonical;
}

/** Server-only: reads root CHANGELOG.md at build time. Do not import from client components. */
export function readReleasesFromChangelog(): ReleaseEntry[] {
  const resolved = assertReadableChangelogPath();
  const content = fs.readFileSync(resolved, "utf8");
  return parseChangelogContent(content);
}
