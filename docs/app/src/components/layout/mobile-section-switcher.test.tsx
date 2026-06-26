import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MobileSectionSwitcher } from "@/components/layout/mobile-section-switcher";
import { MOBILE_NAV_SECTIONS } from "@/lib/site-nav-config";

vi.mock("fumadocs-ui/components/ui/collapsible", () => ({
  Collapsible: ({
    children,
    open,
  }: Readonly<{ children: React.ReactNode; open?: boolean }>) => (
    <div data-open={open ? "true" : "false"}>{children}</div>
  ),
  CollapsibleTrigger: ({
    children,
    ...props
  }: Readonly<{ children: React.ReactNode }>) => (
    <button type="button" {...props}>
      {children}
    </button>
  ),
  CollapsibleContent: ({
    children,
  }: Readonly<{ children: React.ReactNode }>) => <div>{children}</div>,
}));

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    onClick,
    ...props
  }: Readonly<{
    children: React.ReactNode;
    href: string;
    onClick?: () => void;
  }>) => (
    <a href={href} onClick={onClick} {...props}>
      {children}
    </a>
  ),
}));

afterEach(() => {
  cleanup();
});

describe("MobileSectionSwitcher", () => {
  it("renders the active section title", () => {
    render(
      <MobileSectionSwitcher
        sections={MOBILE_NAV_SECTIONS}
        activeSectionId="blog"
        onSelect={vi.fn()}
      />,
    );

    const trigger = screen.getByRole("button");
    expect(within(trigger).getByText("Blog")).toBeInTheDocument();
    expect(within(trigger).getByText("Engineering notes")).toBeInTheDocument();
  });

  it("expands sections and calls onSelect when a link is clicked", async () => {
    const onSelect = vi.fn();

    render(
      <MobileSectionSwitcher
        sections={MOBILE_NAV_SECTIONS}
        activeSectionId="docs"
        onSelect={onSelect}
      />,
    );

    fireEvent.click(screen.getByRole("button"));
    fireEvent.click(screen.getByRole("link", { name: /Roadmap/i }));

    await waitFor(() => {
      expect(onSelect).toHaveBeenCalledTimes(1);
    });
  });
});
