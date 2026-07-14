import fs from "node:fs";
import path from "node:path";

import { parseChangelogContent } from "./parse-changelog";
import type { ReleaseEntry } from "./types";

/** Server-only: reads root CHANGELOG.md at build time. Do not import from client components. */
export function readReleasesFromChangelog(
  changelogPath?: string,
): ReleaseEntry[] {
  const resolved =
    changelogPath ??
    path.resolve(/*turbopackIgnore: true*/ process.cwd(), "../CHANGELOG.md");
  const content = fs.readFileSync(resolved, "utf8");
  return parseChangelogContent(content);
}
