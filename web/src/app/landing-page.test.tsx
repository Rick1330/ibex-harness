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
  it("renders landing sections matching Paper/Ink structure", () => {
    render(<HomePage />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /LLMs/i,
    );
    expect(document.querySelector(".ibex-landing")).toBeInTheDocument();
    expect(screen.getByTestId("hero-terminal-card")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /silent failure/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /one gate/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /on your machine/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /at the proxy/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Skip to content/i })).toHaveAttribute(
      "href",
      "#overview",
    );
  });
});
