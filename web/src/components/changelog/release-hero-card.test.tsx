import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ReleaseHeroCard } from "@/components/changelog/release-hero-card";
import { makeRelease } from "@/components/changelog/test-fixtures";

describe("ReleaseHeroCard", () => {
  afterEach(() => cleanup());

  it("renders version, UTC date, and GitHub CTAs", () => {
    render(
      <ReleaseHeroCard
        release={makeRelease({ version: "0.1.0", date: "2026-07-13" })}
      />,
    );

    expect(screen.getByText("v0.1.0")).toBeInTheDocument();
    expect(screen.getByText("July 13, 2026")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /GitHub Release/i })).toHaveAttribute(
      "href",
      "https://github.com/Rick1330/ibex-harness/releases/tag/v0.1.0",
    );
    expect(screen.getByRole("link", { name: /All tags/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /SBOM assets/i })).toBeInTheDocument();
  });
});
