import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const setTheme = vi.fn();

vi.mock("next-themes", () => ({
  useTheme: () => ({ theme: "light", setTheme }),
}));

import { ThemeToggle } from "@/components/theme-toggle";

afterEach(() => {
  cleanup();
  setTheme.mockClear();
});

describe("ThemeToggle", () => {
  beforeEach(() => {
    setTheme.mockClear();
  });

  it("renders compact cycle control and desktop segmented control", async () => {
    render(<ThemeToggle />);

    const compact = await screen.findByRole("button", {
      name: /Theme: Light\. Click to switch/i,
    });
    expect(compact).toHaveAttribute("data-theme-toggle", "compact");

    const group = screen.getByRole("radiogroup", { name: "Theme" });
    expect(group).toHaveAttribute("data-theme-toggle", "segmented");
    expect(screen.getByRole("radio", { name: "System" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Light" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Dark" })).toBeInTheDocument();
  });

  it("cycles theme from the compact button", async () => {
    render(<ThemeToggle />);

    const compact = await screen.findByRole("button", {
      name: /Theme: Light\. Click to switch/i,
    });
    fireEvent.click(compact);
    expect(setTheme).toHaveBeenCalledWith("dark");
  });
});
