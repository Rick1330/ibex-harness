import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SiteNavLinks } from "@/components/site-nav-links";
import { LANDING_SITE_URL } from "@/lib/site-nav-config";

describe("SiteNavLinks", () => {
  it("includes external link to ibexharness.com", () => {
    render(<SiteNavLinks pathname="/docs/getting-started/introduction" variant="desktop" />);

    const home = screen.getByRole("link", { name: "Home" });
    expect(home).toHaveAttribute("href", LANDING_SITE_URL);
    expect(home).not.toHaveAttribute("target");
  });
});
