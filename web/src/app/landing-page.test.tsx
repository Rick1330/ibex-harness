import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/landing/ascii-background", () => ({
  AsciiBackground: () => <div data-testid="ascii-bg" />,
}));
vi.mock("@/components/landing/ibex-video", () => ({
  IbexVideo: () => <div data-testid="ibex-video" />,
}));
vi.mock("@/components/landing/reveal", () => ({
  Reveal: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import HomePage from "@/app/page";

describe("HomePage", () => {
  it("renders landing shell with hero copy", async () => {
    const Page = HomePage;
    render(<Page />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/LLMs/);
    expect(document.querySelector(".ibex-landing")).toBeInTheDocument();
    expect(screen.getByText(/Put agent memory at the proxy/)).toBeInTheDocument();
  });
});
