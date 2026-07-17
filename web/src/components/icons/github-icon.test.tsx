import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { GithubIcon } from "@/components/icons/github-icon";

afterEach(() => {
  cleanup();
});

describe("GithubIcon", () => {
  it("renders an svg and forwards className and strokeWidth", () => {
    const { container } = render(
      <GithubIcon className="size-4" strokeWidth={1.5} data-testid="github-icon" />,
    );

    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute("data-testid", "github-icon");
    expect(svg).toHaveClass("size-4");
    expect(svg).toHaveAttribute("stroke-width", "1.5");
    expect(svg).toHaveAttribute("aria-hidden");
  });
});
