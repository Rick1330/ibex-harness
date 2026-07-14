import type { ReleaseType } from "@/lib/changelog";

const BADGE_BY_TYPE: Readonly<Record<ReleaseType, string>> = {
  major:
    "rounded-sm bg-text-primary px-2.5 py-0.5 font-mono text-xs font-bold text-canvas",
  minor:
    "rounded-sm border border-border bg-panel px-2.5 py-0.5 font-mono text-xs font-bold text-text-primary",
  patch:
    "rounded-sm border border-border bg-panel-raised px-2.5 py-0.5 font-mono text-xs font-bold text-text-secondary",
};

/** Maps a parsed release type to its Matte Graphite badge class. */
export function releaseTypeBadgeClass(type: ReleaseType): string {
  if (type === "major") return BADGE_BY_TYPE.major;
  if (type === "minor") return BADGE_BY_TYPE.minor;
  return BADGE_BY_TYPE.patch;
}
