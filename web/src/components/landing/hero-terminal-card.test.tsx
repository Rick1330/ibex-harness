import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HeroTerminalCard } from "@/components/landing/hero-terminal-card";

function mockMatchMedia(matches = false) {
  Object.defineProperty(globalThis, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: matches && query.includes("prefers-reduced-motion"),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

beforeEach(() => {
  mockMatchMedia(false);
});

afterEach(() => {
  cleanup();
});

describe("HeroTerminalCard", () => {
  it("renders default request tab content", () => {
    render(<HeroTerminalCard />);
    const card = screen.getByTestId("hero-terminal-card");

    expect(card).toBeInTheDocument();
    expect(within(card).getByText("/v1/chat/completions")).toBeInTheDocument();
    expect(
      within(card).getByRole("tab", { name: "request.http" }),
    ).toHaveAttribute("aria-selected", "true");
  });

  it("switches tabs when a tab button is clicked", () => {
    render(<HeroTerminalCard />);
    const card = screen.getByTestId("hero-terminal-card");

    fireEvent.click(within(card).getByRole("tab", { name: "trace.log" }));
    expect(
      within(card).getByRole("tab", { name: "trace.log" }),
    ).toHaveAttribute("aria-selected", "true");
    expect(within(card).getByText(/trace_id=/i)).toBeInTheDocument();
  });

  it("does not auto-cycle when reduced motion is preferred", () => {
    mockMatchMedia(true);
    vi.useFakeTimers();
    render(<HeroTerminalCard />);
    vi.advanceTimersByTime(7000);

    const card = screen.getByTestId("hero-terminal-card");
    expect(
      within(card).getByRole("tab", { name: "request.http" }),
    ).toHaveAttribute("aria-selected", "true");

    vi.useRealTimers();
  });
});
