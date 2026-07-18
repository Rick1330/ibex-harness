import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Callout } from "@/components/mdx/callout";

afterEach(() => {
  cleanup();
});

describe("Callout", () => {
  it("renders declared variants and warn alias", () => {
    const { rerender } = render(
      <Callout type="warning" title="Caution">
        Watch out
      </Callout>,
    );
    expect(screen.getByText("Caution")).toBeInTheDocument();
    expect(document.querySelector('[data-type="warning"]')).toBeTruthy();

    rerender(
      <Callout type="warn" title="Alias">
        Same as warning
      </Callout>,
    );
    expect(document.querySelector('[data-type="warn"]')).toBeTruthy();

    rerender(
      <Callout type="success" title="Done">
        Ok
      </Callout>,
    );
    expect(document.querySelector('[data-type="success"]')).toBeTruthy();
  });

  it("falls back to note for unknown types", () => {
    render(
      <Callout type="not-a-real-type" title="Fallback">
        Body
      </Callout>,
    );
    expect(screen.getByText("Fallback")).toBeInTheDocument();
    expect(
      document.querySelector('[data-type="not-a-real-type"]'),
    ).toBeTruthy();
  });
});
