import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { LandingMarquee } from "@/components/landing/landing-marquee";
import { MARQUEE } from "@/lib/landing-content";

afterEach(() => {
  cleanup();
});

describe("LandingMarquee", () => {
  it("renders a single-line marquee track with duplicated tags", () => {
    const { container } = render(<LandingMarquee />);
    const root = screen.getByTestId("landing-marquee");
    expect(root).toHaveClass("overflow-hidden");
    expect(container.querySelector(".marquee-track")).toBeTruthy();
    expect(container.querySelector(".marquee-track")).toHaveClass(
      "w-max",
      "whitespace-nowrap",
    );
    // Two copies of each tag for seamless -50% loop
    for (const tag of MARQUEE) {
      expect(screen.getAllByText(tag)).toHaveLength(2);
    }
  });
});
