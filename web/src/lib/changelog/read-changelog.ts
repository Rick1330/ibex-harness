import { CHANGELOG_MARKDOWN } from "./changelog-content.generated";
import { parseChangelogContent } from "./parse-changelog";
import type { ReleaseEntry } from "./types";

/** Server-only: parses changelog embedded at build time. Do not import from client components. */
export function readReleasesFromChangelog(): ReleaseEntry[] {
  return parseChangelogContent(CHANGELOG_MARKDOWN);
}
