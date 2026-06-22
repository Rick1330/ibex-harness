import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { MermaidAscii } from "./mermaid-ascii";

afterEach(() => {
  cleanup();
});

describe("MermaidAscii", () => {
  it("renders ascii in code when provided", () => {
    const { container } = render(
      <MermaidAscii
        ascii={"A --> B"}
        source={"graph LR\nA --> B"}
      />,
    );

    const pre = container.querySelector("[data-mermaid-ascii]");
    expect(pre).toHaveTextContent("A --> B");
    expect(
      screen.queryByText(/ASCII conversion unavailable/i),
    ).not.toBeInTheDocument();
  });

  it("shows fallback note when ascii is missing but source exists", () => {
    const { container } = render(
      <MermaidAscii source={"graph LR\nA --> B"} />,
    );

    const pre = container.querySelector("[data-mermaid-ascii]");
    expect(pre).toHaveTextContent("graph LR");
    expect(
      screen.getByText(/ASCII conversion unavailable/i),
    ).toBeInTheDocument();
  });

  it("renders optional caption", () => {
    render(
      <MermaidAscii
        ascii={"A --> B"}
        source={"graph LR\nA --> B"}
        caption="Request flow"
      />,
    );

    expect(screen.getByText("Request flow")).toBeInTheDocument();
  });

  it("exposes accessible label for screen readers", () => {
    const { container } = render(
      <MermaidAscii
        ascii={"A --> B"}
        source={"graph LR\nA --> B"}
      />,
    );

    const figure = container.querySelector("figure");
    expect(figure).not.toBeNull();
    const label = within(figure as HTMLElement).getByText(
      "Mermaid diagram: graph LR",
    );
    expect(label).toHaveClass("sr-only");
  });
});
