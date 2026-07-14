import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChangelogScopeFilter } from "@/components/changelog/changelog-scope-filter";

describe("ChangelogScopeFilter", () => {
  afterEach(() => cleanup());

  it("renders nothing when scopes are empty", () => {
    const { container } = render(
      <ChangelogScopeFilter scopes={[]} activeScope={null} onChange={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("calls onChange for all and scope chips", () => {
    const onChange = vi.fn();
    render(
      <ChangelogScopeFilter
        scopes={["auth", "proxy"]}
        activeScope="auth"
        onChange={onChange}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "all" }));
    expect(onChange).toHaveBeenCalledWith(null);

    fireEvent.click(screen.getByRole("button", { name: "proxy" }));
    expect(onChange).toHaveBeenCalledWith("proxy");

    fireEvent.click(screen.getByRole("button", { name: "auth" }));
    expect(onChange).toHaveBeenCalledWith(null);
  });
});
