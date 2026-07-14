import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeRelease } from "@/components/changelog/test-fixtures";

vi.mock("@/lib/changelog/read-changelog", () => ({
  readReleasesFromChangelog: vi.fn(),
}));

vi.mock("@/components/changelog/release-notes-panel", () => ({
  ReleaseNotesPanel: ({ release }: { release: { version: string } }) => (
    <div data-testid={`notes-${release.version}`}>notes for {release.version}</div>
  ),
}));

vi.mock("@/components/changelog/release-timeline", () => ({
  ReleaseTimeline: ({ releases }: { releases: { version: string }[] }) => (
    <section>
      <h2>Previous releases</h2>
      <div data-testid="older-versions">
        {releases.map((release) => release.version).join(",")}
      </div>
    </section>
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

    expect(screen.getByText(/No tagged releases yet/i)).toBeInTheDocument();
    expect(screen.queryByText("v0.1.0")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Complete machine-readable history"),
    ).not.toBeInTheDocument();
  });

  it("renders latest release hero and notes without previous timeline", () => {
    mockRead.mockReturnValue([makeRelease({ version: "0.1.0" })]);
    render(<ReleasesPage />);

    expect(screen.getByText("Release history")).toBeInTheDocument();
    expect(screen.getByText("v0.1.0")).toBeInTheDocument();
    expect(screen.getByTestId("notes-0.1.0")).toBeInTheDocument();
    expect(screen.queryByText("Previous releases")).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /RELEASING\.md/i }),
    ).toHaveAttribute(
      "href",
      "https://github.com/Rick1330/ibex-harness/blob/main/web/engineering/RELEASING.md",
    );
    expect(
      screen.getByText("Complete machine-readable history"),
    ).toBeInTheDocument();
  });

  it("renders older releases in the previous-releases timeline", () => {
    mockRead.mockReturnValue([
      makeRelease({ version: "0.2.0" }),
      makeRelease({ version: "0.1.0", type: "minor", date: "2026-07-01" }),
    ]);
    render(<ReleasesPage />);

    expect(screen.getByText("v0.2.0")).toBeInTheDocument();
    expect(screen.getByText("Previous releases")).toBeInTheDocument();
    expect(screen.getByTestId("older-versions")).toHaveTextContent("0.1.0");
  });
});
