import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("fumadocs-ui/components/ui/collapsible", async () => {
  const React = await import("react");

  const CollapsibleContext = React.createContext<{
    open: boolean;
    onOpenChange?: (next: boolean) => void;
  }>({ open: false });

  function Collapsible({
    children,
    open = false,
    onOpenChange,
  }: {
    children: React.ReactNode;
    open?: boolean;
    onOpenChange?: (next: boolean) => void;
  }) {
    return React.createElement(
      CollapsibleContext.Provider,
      { value: { open, onOpenChange } },
      children,
    );
  }

  function CollapsibleTrigger({
    children,
    className,
  }: {
    children: React.ReactNode;
    className?: string;
  }) {
    const ctx = React.useContext(CollapsibleContext);
    return React.createElement(
      "button",
      {
        type: "button",
        className,
        onClick: () => ctx.onOpenChange?.(!ctx.open),
      },
      children,
    );
  }

  function CollapsibleContent({
    children,
    className,
  }: {
    children: React.ReactNode;
    className?: string;
  }) {
    const ctx = React.useContext(CollapsibleContext);
    if (!ctx.open) return null;
    return React.createElement("div", { className }, children);
  }

  return { Collapsible, CollapsibleTrigger, CollapsibleContent };
});

import { ReleaseTimeline } from "@/components/changelog/release-timeline";
import { makeRelease } from "@/components/changelog/test-fixtures";

describe("ReleaseTimeline", () => {
  afterEach(() => cleanup());

  it("renders nothing for an empty list", () => {
    const { container } = render(<ReleaseTimeline releases={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("lists previous releases and expands details on click", () => {
    render(
      <ReleaseTimeline
        releases={[
          makeRelease({ version: "0.0.1", type: "patch", date: "2026-06-01" }),
        ]}
      />,
    );

    expect(screen.getByText("Previous releases")).toBeInTheDocument();
    expect(screen.getByText("v0.0.1")).toBeInTheDocument();
    expect(screen.getByText("June 1, 2026")).toBeInTheDocument();
    expect(screen.queryByText("token creation")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /v0\.0\.1/i }));
    expect(screen.getByText("token creation")).toBeInTheDocument();
  });
});
