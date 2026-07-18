import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LandingShell } from "@/components/landing/landing-shell";

describe("LandingShell", () => {
  it("renders children inside shell-token wrapper and pre", () => {
    const { container } = render(
      <LandingShell>git clone ibex-harness</LandingShell>,
    );

    expect(screen.getByText("git clone ibex-harness")).toBeInTheDocument();
    const wrapper = container.firstElementChild;
    expect(wrapper).toHaveClass("code-shell");
    expect(wrapper?.querySelector("pre")).toHaveClass("code-shell-body");
  });

  it("applies custom className on the wrapper", () => {
    const { container } = render(
      <LandingShell className="mt-6 max-w-lg">command</LandingShell>,
    );

    expect(container.firstElementChild).toHaveClass("mt-6", "max-w-lg");
  });

  it("uses compact padding and text size when compact is true", () => {
    const { container } = render(
      <LandingShell compact>compact command</LandingShell>,
    );
    expect(container.firstElementChild?.querySelector("pre")).toHaveClass(
      "p-3",
      "text-[11px]",
    );
  });
});
