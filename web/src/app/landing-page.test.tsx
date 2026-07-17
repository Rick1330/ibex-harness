import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

beforeEach(() => {
  Object.defineProperty(globalThis, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation(() => ({
      matches: false,
      media: "",
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

import HomePage from "@/app/page";

describe("HomePage", () => {
  it("renders design-guide sections §01–§09", () => {
    render(<HomePage />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /in production/i,
    );
    expect(screen.getByTestId("hero-terminal-card")).toBeInTheDocument();
    expect(screen.getByText(/§02 · CAPABILITIES/i)).toBeInTheDocument();
    expect(screen.getByText(/§03 · REQUEST PATH/i)).toBeInTheDocument();
    expect(screen.getByText(/§04 · BENCHMARKS/i)).toBeInTheDocument();
    expect(screen.getByText(/§05 · LOCAL STACK/i)).toBeInTheDocument();
    expect(screen.getByText(/§06 · FROM THE SPEC/i)).toBeInTheDocument();
    expect(screen.getByText(/§07 · CHANGELOG/i)).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /at the proxy/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Skip to content/i })).toHaveAttribute(
      "href",
      "#overview",
    );
  });
});
