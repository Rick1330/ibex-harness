import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { MermaidAscii } from "./mermaid-ascii";

afterEach(() => {
  cleanup();
});

describe("MermaidAscii", () => {
  it("renders ascii in code when provided", () => {
    render(
      <MermaidAscii
        ascii={"A --> B"}
        source={"graph LR\nA --> B"}
      />,
    );

    expect(screen.getByText("A --> B", { selector: "code" })).toBeInTheDocument();
    expect(
      screen.queryByText(/ASCII conversion unavailable/i),
    ).not.toBeInTheDocument();
  });

  it("shows fallback note when ascii is missing but source exists", () => {
    render(<MermaidAscii source={"graph LR\nA --> B"} />);

    expect(
      screen.getByText((_, element) => {
        return (
          element?.tagName === "CODE" &&
          element.textContent?.includes("graph LR") === true
        );
      }),
    ).toBeInTheDocument();
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
    render(
      <MermaidAscii
        ascii={"A --> B"}
        source={"graph LR\nA --> B"}
      />,
    );

    const figure = screen.getByRole("figure");
    const label = within(figure).getByText("Mermaid diagram: graph LR");
    expect(label).toHaveClass("sr-only");
  });
});
