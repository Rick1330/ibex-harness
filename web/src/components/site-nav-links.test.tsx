import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SiteNavLinks } from "@/components/site-nav-links";

afterEach(() => {
  cleanup();
});

describe("SiteNavLinks", () => {
  it("renders guide nav links without Home", () => {
    render(
      <SiteNavLinks
        pathname="/docs/getting-started/introduction"
        variant="desktop"
      />,
    );

    expect(screen.queryByRole("link", { name: "Home" })).toBeNull();
    expect(screen.getByRole("link", { name: "Docs" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Benchmarks" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Blog" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Changelog" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Roadmap" })).toBeInTheDocument();
  });

  it("marks docs active with aria-current", () => {
    render(
      <SiteNavLinks
        pathname="/docs/getting-started/introduction"
        variant="desktop"
      />,
    );

    expect(screen.getByRole("link", { name: "Docs" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});
