import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SiteNavLinks } from "@/components/site-nav-links";
import { LANDING_SITE_URL } from "@/lib/site-nav-config";

afterEach(() => {
  cleanup();
});

describe("SiteNavLinks", () => {
  it("includes internal home link", () => {
    render(<SiteNavLinks pathname="/docs/getting-started/introduction" variant="desktop" />);

    const home = screen.getByRole("link", { name: "Home" });
    expect(home).toHaveAttribute("href", LANDING_SITE_URL);
    expect(home).not.toHaveAttribute("target");
  });

  it("marks home active on landing path", () => {
    render(<SiteNavLinks pathname="/" variant="desktop" />);

    const home = screen.getByRole("link", { name: "Home" });
    expect(home.className).toContain("text-foreground");
  });
});
