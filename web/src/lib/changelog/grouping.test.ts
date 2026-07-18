import { describe, expect, it } from "vitest";

import {
  buildChangelogNav,
  editorialSectionLabel,
  isNewRelease,
  quarterAnchor,
} from "@/lib/changelog/grouping";
import type { ReleaseEntry } from "@/lib/changelog/types";

function release(
  partial: Partial<ReleaseEntry> & Pick<ReleaseEntry, "version" | "date">,
): ReleaseEntry {
  return {
    type: "minor",
    summary: null,
    sections: [],
    ...partial,
  };
}

describe("changelog grouping", () => {
  it("maps section titles to editorial labels", () => {
    expect(editorialSectionLabel("Features")).toBe("Added");
    expect(editorialSectionLabel("Bug Fixes")).toBe("Fixed");
    expect(editorialSectionLabel("Breaking Changes")).toBe("Breaking");
  });

  it("marks releases newer than 14 days", () => {
    const now = new Date("2026-07-18T12:00:00Z");
    expect(isNewRelease("2026-07-10", now)).toBe(true);
    expect(isNewRelease("2026-06-01", now)).toBe(false);
  });

  it("builds year → quarter nav newest first", () => {
    const groups = buildChangelogNav([
      release({ version: "0.3.0", date: "2026-07-14", type: "minor" }),
      release({ version: "0.2.0", date: "2026-04-02", type: "minor" }),
      release({ version: "0.1.0", date: "2025-11-01", type: "major" }),
    ]);

    expect(groups.map((g) => g.year)).toEqual([2026, 2025]);
    expect(groups[0]?.quarters.map((q) => q.anchor)).toEqual([
      quarterAnchor(2026, 3),
      quarterAnchor(2026, 2),
    ]);
  });
});
