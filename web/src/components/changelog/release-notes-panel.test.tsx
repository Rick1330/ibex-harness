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

import { ReleaseNotesPanel } from "@/components/changelog/release-notes-panel";
import { makeChangeItem, makeRelease, makeSection } from "@/components/changelog/test-fixtures";

describe("ReleaseNotesPanel", () => {
  afterEach(() => cleanup());

  it("shows scope filter when multiple scopes exist", () => {
    render(<ReleaseNotesPanel release={makeRelease({ version: "0.1.0" })} />);
    expect(screen.getByRole("button", { name: "all" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "auth" })).toBeInTheDocument();
  });

  it("hides scope filter when showScopeFilter is false", () => {
    render(
      <ReleaseNotesPanel
        release={makeRelease({ version: "0.1.0" })}
        showScopeFilter={false}
      />,
    );
    expect(screen.queryByRole("button", { name: "all" })).not.toBeInTheDocument();
  });

  it("filters section items by selected scope", () => {
    render(<ReleaseNotesPanel release={makeRelease({ version: "0.1.0" })} />);

    expect(screen.getByText("token creation")).toBeInTheDocument();
    expect(screen.getByText("rate limit skeleton")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "auth" }));
    expect(screen.getByText("token creation")).toBeInTheDocument();
    expect(screen.queryByText("rate limit skeleton")).not.toBeInTheDocument();
  });

  it("omits filter for a single-scope release", () => {
    render(
      <ReleaseNotesPanel
        release={makeRelease({
          version: "0.2.0",
          sections: [
            makeSection("Features", [
              makeChangeItem({ scope: "auth", description: "only auth" }),
            ]),
          ],
        })}
      />,
    );
    expect(screen.queryByRole("button", { name: "all" })).not.toBeInTheDocument();
    expect(screen.getByText("only auth")).toBeInTheDocument();
  });
});
