import fs from "node:fs";
import path from "node:path";

import { parseChangelogContent } from "./parse-changelog";
import type { ReleaseEntry } from "./types";

const REPO_ROOT = path.resolve(process.cwd(), "..");
const CHANGELOG_FILE = path.join(REPO_ROOT, "CHANGELOG.md");

/** Rejects symlink escapes and non-CHANGELOG targets before reading. */
function assertReadableChangelogPath(): void {
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
}

/** Server-only: reads root CHANGELOG.md at build time. Do not import from client components. */
export function readReleasesFromChangelog(): ReleaseEntry[] {
  assertReadableChangelogPath();
  // Fixed build-time path; assertReadableChangelogPath resolves realpath and enforces repo boundary.
  const content = fs.readFileSync(CHANGELOG_FILE, "utf8"); // nosemgrep: javascript.lang.security.audit.detect-non-literal-fs-filename.detect-non-literal-fs-filename
  return parseChangelogContent(content);
}
