import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/landing/reveal", () => ({
  Reveal: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

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
  it("renders landing sections with hero copy and terminal card", async () => {
    const Page = HomePage;
    render(<Page />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /in production/i,
    );
    expect(document.querySelector(".ibex-landing")).toBeInTheDocument();
    expect(screen.getByTestId("hero-terminal-card")).toBeInTheDocument();
    expect(screen.getByText(/Put agent memory at the proxy/i)).toBeInTheDocument();
    expect(screen.getByText(/§02 · CAPABILITIES/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Skip to content/i })).toHaveAttribute(
      "href",
      "#overview",
    );
  });
});
