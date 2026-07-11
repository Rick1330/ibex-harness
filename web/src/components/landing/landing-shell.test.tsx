import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LandingShell } from "@/components/landing/landing-shell";

describe("LandingShell", () => {
  it("renders children inside ascii-frame wrapper and pre", () => {
    const { container } = render(
      <LandingShell>git clone ibex-harness</LandingShell>,
    );

    expect(screen.getByText("git clone ibex-harness")).toBeInTheDocument();
    const wrapper = container.firstElementChild;
    expect(wrapper).toHaveClass("ascii-frame", "overflow-x-auto", "bg-card");
    expect(wrapper?.querySelector("pre")).toHaveClass("font-mono", "p-4", "text-[12px]");
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

  it("uses primary surface styling when requested", () => {
    const { container } = render(
      <LandingShell surface="primary">primary command</LandingShell>,
    );

    expect(container.firstElementChild).toHaveClass(
      "bg-primary-foreground/10",
      "text-primary-foreground",
    );
  });
});
