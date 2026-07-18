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

  class MockIntersectionObserver {
    observe = vi.fn();
    unobserve = vi.fn();
    disconnect = vi.fn();
  }
  vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
});

import HomePage from "@/app/page";

describe("HomePage", () => {
  it("renders section rail, hero shell, and guide sections", () => {
    render(<HomePage />);

    expect(screen.getByLabelText(/Section rail/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /§01/i })).toHaveAttribute(
      "href",
      "#overview",
    );
    expect(screen.getByRole("link", { name: /§02/i })).toHaveAttribute(
      "href",
      "#capabilities",
    );
    expect(screen.getByRole("link", { name: /§03/i })).toHaveAttribute(
      "href",
      "#request-path",
    );
    expect(screen.getByRole("link", { name: /§04/i })).toHaveAttribute(
      "href",
      "#local-stack",
    );

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/LLMs/i);
    expect(screen.getByTestId("hero-terminal")).toBeInTheDocument();
    expect(screen.getByTestId("hero-shell-column")).toBeInTheDocument();

    expect(screen.getByText(/§02 · CAPABILITIES/i)).toBeInTheDocument();
    expect(screen.getByText(/§03 · REQUEST PATH/i)).toBeInTheDocument();
    expect(screen.getByText(/§04 · LOCAL STACK/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Key stats/i)).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /at the proxy/i }),
    ).toBeInTheDocument();
  });
});
