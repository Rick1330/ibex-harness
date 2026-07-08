import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AsciiBackground } from "@/components/landing/ascii-background";

describe("AsciiBackground", () => {
  it("renders tiled ascii backdrop", () => {
    const { container } = render(<AsciiBackground />);
    expect(container.querySelector(".ascii-tile-bg")).toBeInTheDocument();
  });
});
