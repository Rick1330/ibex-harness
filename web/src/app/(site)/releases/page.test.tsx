import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeRelease } from "@/components/changelog/test-fixtures";

vi.mock("@/lib/changelog/read-changelog", () => ({
  readReleasesFromChangelog: vi.fn(),
}));

vi.mock("@/components/changelog/changelog-view", () => ({
  ChangelogView: ({ releases }: { releases: { version: string }[] }) => (
    <div data-testid="changelog-view">
      {releases.length === 0
        ? "No tagged releases yet"
        : releases.map((r) => `v${r.version}`).join(",")}
    </div>
  ),
}));

import ReleasesPage from "@/app/(site)/releases/page";
import { readReleasesFromChangelog } from "@/lib/changelog/read-changelog";

const mockRead = vi.mocked(readReleasesFromChangelog);

describe("ReleasesPage", () => {
  afterEach(() => {
    cleanup();
    mockRead.mockReset();
  });

  it("shows empty state when there are no releases", () => {
    mockRead.mockReturnValue([]);
    render(<ReleasesPage />);

    expect(screen.getByRole("heading", { name: "Changelog" })).toBeInTheDocument();
    expect(screen.getByTestId("changelog-view")).toHaveTextContent(
      /No tagged releases yet/i,
    );
  });

  it("renders changelog intro and feed for latest release", () => {
    mockRead.mockReturnValue([makeRelease({ version: "0.1.0" })]);
    render(<ReleasesPage />);

    expect(screen.getByRole("heading", { name: "Changelog" })).toBeInTheDocument();
    expect(screen.getByTestId("changelog-view")).toHaveTextContent("v0.1.0");
    expect(
      screen.getByRole("link", { name: /RELEASING\.md/i }),
    ).toHaveAttribute(
      "href",
      "https://github.com/Rick1330/ibex-harness/blob/main/web/engineering/RELEASING.md",
    );
  });

  it("passes older releases into the changelog view", () => {
    mockRead.mockReturnValue([
      makeRelease({ version: "0.2.0" }),
      makeRelease({ version: "0.1.0", type: "minor", date: "2026-07-01" }),
    ]);
    render(<ReleasesPage />);

    expect(screen.getByTestId("changelog-view")).toHaveTextContent(
      "v0.2.0,v0.1.0",
    );
  });
});
