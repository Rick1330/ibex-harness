import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BrandLockup } from "@/components/brand-lockup";

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
  it("uses the default docs-home aria label", () => {
    render(<BrandLockup />);

    expect(
      screen.getByRole("link", { name: "IBEX Harness docs home" }),
    ).toBeInTheDocument();
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
