import { describe, expect, it } from "vitest";

import {
  parseChangeItem,
  parseChangelogContent,
  parseReleaseType,
} from "./parse-changelog";

const SAMPLE_BULLET =
  "* **auth:** token creation and management (m1.1.4) ([#47](https://github.com/Rick1330/ibex-harness/issues/47)) ([0ada899](https://github.com/Rick1330/ibex-harness/commit/0ada899a19631536aa730dda216f328322ecb25e))";

const SAMPLE_NO_SCOPE =
  "* move integration helpers into repository_test; gofmt chat cases ([4de673c](https://github.com/Rick1330/ibex-harness/commit/4de673cc06bb21b470eb01b40105b2d255f81153))";

describe("parseReleaseType", () => {
  it("classifies pre-1.0 minor", () => {
    expect(parseReleaseType("0.1.0")).toBe("minor");
  });

  it("classifies patch", () => {
    expect(parseReleaseType("0.0.1")).toBe("patch");
  });

  it("classifies major", () => {
    expect(parseReleaseType("1.0.0")).toBe("major");
  });

  it("classifies 1.1.0 as minor (most-specific non-zero segment)", () => {
    expect(parseReleaseType("1.1.0")).toBe("minor");
  });

  it("classifies 1.1.1 as patch (most-specific non-zero segment)", () => {
    expect(parseReleaseType("1.1.1")).toBe("patch");
  });
});

describe("parseChangeItem", () => {
  it("extracts scope, description, issue, and commit", () => {
    const item = parseChangeItem(SAMPLE_BULLET);
    expect(item).not.toBeNull();
    expect(item?.scope).toBe("auth");
    expect(item?.description).toBe("token creation and management");
    expect(item?.issueNumber).toBe(47);
    expect(item?.commitSha).toBe("0ada899");
    expect(item?.priority).toBe("standard");
  });

  it("handles bullets without scope", () => {
    const item = parseChangeItem(SAMPLE_NO_SCOPE);
    expect(item?.scope).toBeNull();
    expect(item?.description).toContain("move integration helpers");
    expect(item?.commitSha).toBe("4de673c");
  });

  it("strips milestone markers without regex ReDoS pattern", () => {
    const item = parseChangeItem(
      "* **db:** users and agents schema (m1.1.7) ([#57](https://github.com/Rick1330/ibex-harness/issues/57)) ([59e7e04](https://github.com/Rick1330/ibex-harness/commit/59e7e04))",
    );
    expect(item?.description).toBe("users and agents schema");
  });

  it("strips multiple milestones and skips unrelated (m text", () => {
    const item = parseChangeItem(
      "* **auth:** login (m1.2.3) and (more info) (m2.0.1) flow ([#1](https://github.com/Rick1330/ibex-harness/issues/1)) ([abc1234](https://github.com/Rick1330/ibex-harness/commit/abc1234567890))",
    );
    expect(item?.description).toBe("login and (more info) flow");
  });

  it("finds issue link after skipping commit-only wrapped links", () => {
    const item = parseChangeItem(
      "* **proxy:** rate limit ([abc1234](https://github.com/Rick1330/ibex-harness/commit/abc1234567890)) ([#99](https://github.com/Rick1330/ibex-harness/issues/99)) ([def5678](https://github.com/Rick1330/ibex-harness/commit/def5678901234))",
    );
    expect(item?.issueNumber).toBe(99);
    expect(item?.commitSha).toBe("def5678");
  });

  it("marks internal scopes", () => {
    const item = parseChangeItem(
      "* **ci:** harden version release workflow reporting ([#230](https://github.com/Rick1330/ibex-harness/issues/230)) ([41d80e9](https://github.com/Rick1330/ibex-harness/commit/41d80e9))",
    );
    expect(item?.scope).toBe("ci");
    expect(item?.priority).toBe("internal");
  });
});

describe("parseChangelogContent", () => {
  const fixture = `
## 0.1.0 (2026-07-13)

### Features

${SAMPLE_BULLET}
* **proxy:** add llm provider interface and registry (m2.1.1) ([0841d4a](https://github.com/Rick1330/ibex-harness/commit/0841d4a))
* **ci:** repair SBOM Grype install ([#213](https://github.com/Rick1330/ibex-harness/issues/213)) ([5a4ea4f](https://github.com/Rick1330/ibex-harness/commit/5a4ea4f))
* **docs:** bootstrap Fumadocs app ([#101](https://github.com/Rick1330/ibex-harness/issues/101)) ([fe58260](https://github.com/Rick1330/ibex-harness/commit/fe58260))
* **docs:** navigation shell ([#106](https://github.com/Rick1330/ibex-harness/issues/106)) ([37c134d](https://github.com/Rick1330/ibex-harness/commit/37c134d))
* **docs:** MDX component catalogue ([#108](https://github.com/Rick1330/ibex-harness/issues/108)) ([1d317f8](https://github.com/Rick1330/ibex-harness/commit/1d317f8))

### Bug Fixes

* **auth:** correct ListTokens keyset cursor pagination ([6563132](https://github.com/Rick1330/ibex-harness/commit/6563132))

## [Unreleased]

### Added

- Manual unreleased entry

## Changelog discipline

Ignored footer.
`;

  it("parses version header and date", () => {
    const releases = parseChangelogContent(fixture);
    expect(releases).toHaveLength(1);
    expect(releases[0].version).toBe("0.1.0");
    expect(releases[0].date).toBe("2026-07-13");
  });

  it("skips unreleased and discipline sections", () => {
    const releases = parseChangelogContent(fixture);
    expect(releases[0].sections).toHaveLength(2);
    expect(releases[0].sections[0].title).toBe("Features");
  });

  it("caps highlights at five per section", () => {
    const releases = parseChangelogContent(fixture);
    const features = releases[0].sections.find((s) => s.title === "Features");
    expect(features?.items).toHaveLength(6);
    expect(features?.highlights.length).toBeLessThanOrEqual(5);
  });

  it("prioritizes user-facing scopes in highlights", () => {
    const releases = parseChangelogContent(fixture);
    const features = releases[0].sections.find((s) => s.title === "Features");
    const highlightScopes = features?.highlights.map((h) => h.scope) ?? [];
    expect(highlightScopes).toContain("auth");
    expect(highlightScopes).toContain("proxy");
    expect(highlightScopes.filter((s) => s === "docs").length).toBeLessThanOrEqual(
      2,
    );
  });
});
