import type { ChangeItem, ReleaseEntry, ReleaseSection } from "@/lib/changelog";

export function makeChangeItem(
  overrides: Partial<ChangeItem> & Pick<ChangeItem, "description">,
): ChangeItem {
  return {
    scope: null,
    issueNumber: null,
    issueUrl: null,
    commitSha: null,
    commitUrl: null,
    priority: "standard",
    ...overrides,
  };
}

export function makeSection(
  title: string,
  items: ChangeItem[],
  highlights?: ChangeItem[],
): ReleaseSection {
  return {
    title,
    items,
    highlights: highlights ?? items.slice(0, 2),
  };
}

export function makeRelease(
  overrides: Partial<ReleaseEntry> & Pick<ReleaseEntry, "version">,
): ReleaseEntry {
  return {
    date: "2026-07-13",
    type: "minor",
    summary: null,
    sections: [
      makeSection("Features", [
        makeChangeItem({
          scope: "auth",
          description: "token creation",
          issueNumber: 47,
          issueUrl: "https://github.com/Rick1330/ibex-harness/issues/47",
          commitSha: "0ada899",
          commitUrl:
            "https://github.com/Rick1330/ibex-harness/commit/0ada899",
        }),
        makeChangeItem({
          scope: "proxy",
          description: "rate limit skeleton",
          issueNumber: 62,
          issueUrl: "https://github.com/Rick1330/ibex-harness/issues/62",
        }),
        makeChangeItem({
          scope: "ci",
          description: "harden workflows",
          priority: "internal",
          commitSha: "abc1234",
          commitUrl: "https://github.com/Rick1330/ibex-harness/commit/abc1234",
        }),
      ]),
    ],
    ...overrides,
  };
}
