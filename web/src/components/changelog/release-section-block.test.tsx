import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

vi.mock("fumadocs-ui/components/ui/collapsible", async () => {
  const React = await import("react");

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

  const CollapsibleContext = React.createContext<{
    open: boolean;
    onOpenChange?: (next: boolean) => void;
  }>({ open: false });

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

import { ReleaseSectionBlock } from "@/components/changelog/release-section-block";
import { makeChangeItem, makeSection } from "@/components/changelog/test-fixtures";

describe("ReleaseSectionBlock", () => {
  afterEach(() => cleanup());

  it("renders nothing when no items match the active scope", () => {
    const { container } = render(
      <ReleaseSectionBlock
        section={makeSection("Features", [
          makeChangeItem({ scope: "auth", description: "token creation" }),
        ])}
        activeScope="proxy"
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows highlights and expands remainder without duplicating highlights", () => {
    const highlight = makeChangeItem({
      scope: "auth",
      description: "token creation",
      issueNumber: 47,
      issueUrl: "https://github.com/Rick1330/ibex-harness/issues/47",
    });
    const extra = makeChangeItem({
      scope: "ci",
      description: "harden workflows",
      commitSha: "abc1234",
      commitUrl: "https://github.com/Rick1330/ibex-harness/commit/abc1234",
    });

    render(
      <ReleaseSectionBlock
        section={makeSection("Features", [highlight, extra], [highlight])}
        activeScope={null}
      />,
    );

    expect(screen.getByText("Features")).toBeInTheDocument();
    expect(screen.getByText("token creation")).toBeInTheDocument();
    expect(screen.queryByText("harden workflows")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Show all 2 changes/i }));
    expect(screen.getByText("harden workflows")).toBeInTheDocument();
    expect(screen.getAllByText("token creation")).toHaveLength(1);
    expect(screen.getByTitle("View commit")).toHaveTextContent("abc1234");
  });
});
