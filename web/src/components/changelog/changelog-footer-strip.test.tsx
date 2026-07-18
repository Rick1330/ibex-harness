import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ChangelogFooterStrip } from "@/components/changelog/changelog-footer-strip";

describe("ChangelogFooterStrip", () => {
  afterEach(() => cleanup());

  it("links to GitHub Releases and CHANGELOG.md", () => {
    render(<ChangelogFooterStrip />);

    expect(screen.getByText("Machine-readable history")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /GitHub Releases/i })).toHaveAttribute(
      "href",
      "https://github.com/Rick1330/ibex-harness/releases",
    );
    expect(screen.getByRole("link", { name: /CHANGELOG\.md/i })).toHaveAttribute(
      "href",
      "https://github.com/Rick1330/ibex-harness/blob/main/CHANGELOG.md",
    );
    expect(screen.getByRole("link", { name: /RSS feed/i })).toHaveAttribute(
      "href",
      "/releases/rss.xml",
    );
  });
});
