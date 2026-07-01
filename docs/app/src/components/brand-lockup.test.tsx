import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BrandLockup } from "@/components/brand-lockup";
import { LANDING_SITE_URL } from "@/lib/site-nav-config";

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: Readonly<{
    children: React.ReactNode;
    href: string;
  }>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

afterEach(() => {
  cleanup();
});

describe("BrandLockup", () => {
  it("links the default brand lockup to the marketing site", () => {
    render(<BrandLockup />);

    expect(screen.getByRole("link", { name: "IBEX Harness home" })).toHaveAttribute(
      "href",
      LANDING_SITE_URL,
    );
  });

  it("accepts a custom aria label for alternate destinations", () => {
    render(
      <BrandLockup
        href="/roadmap"
        ariaLabel="IBEX Harness roadmap home"
      />,
    );

    expect(
      screen.getByRole("link", { name: "IBEX Harness roadmap home" }),
    ).toHaveAttribute("href", "/roadmap");
  });
});
