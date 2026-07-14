import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ChangeItemRow } from "@/components/changelog/change-item-row";
import { makeChangeItem } from "@/components/changelog/test-fixtures";

describe("ChangeItemRow", () => {
  afterEach(() => cleanup());

  it("renders scope, description, and issue link", () => {
    render(
      <ul>
        <ChangeItemRow
          item={makeChangeItem({
            scope: "auth",
            description: "token creation",
            issueNumber: 47,
            issueUrl: "https://github.com/Rick1330/ibex-harness/issues/47",
          })}
        />
      </ul>,
    );

    expect(screen.getByText("auth")).toBeInTheDocument();
    expect(screen.getByText("token creation")).toBeInTheDocument();
    const issue = screen.getByRole("link", { name: "#47" });
    expect(issue).toHaveAttribute(
      "href",
      "https://github.com/Rick1330/ibex-harness/issues/47",
    );
    expect(issue).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("shows commit only when showCommit is enabled", () => {
    const item = makeChangeItem({
      description: "rate limit",
      commitSha: "0ada899",
      commitUrl: "https://github.com/Rick1330/ibex-harness/commit/0ada899",
    });

    const { rerender } = render(
      <ul>
        <ChangeItemRow item={item} />
      </ul>,
    );
    expect(screen.queryByTitle("View commit")).not.toBeInTheDocument();

    rerender(
      <ul>
        <ChangeItemRow item={item} showCommit />
      </ul>,
    );
    expect(screen.getByTitle("View commit")).toHaveTextContent("0ada899");
  });
});
