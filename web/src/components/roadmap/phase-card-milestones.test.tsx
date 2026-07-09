import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PhaseCardMilestones } from "@/components/roadmap/phase-card-milestones";

afterEach(() => {
  cleanup();
});

describe("PhaseCardMilestones", () => {
  it("shows the pending milestones message", () => {
    render(
      <PhaseCardMilestones
        milestonesPending
        showCompleteLabel={false}
        completed={0}
        total={0}
        pct={0}
      />,
    );

    expect(
      screen.getByText("Goals defined — milestones coming soon"),
    ).toBeInTheDocument();
  });

  it("shows Complete instead of 0/0 for completed phases", () => {
    render(
      <PhaseCardMilestones
        milestonesPending={false}
        showCompleteLabel
        completed={0}
        total={0}
        pct={100}
      />,
    );

    expect(screen.getByText("Complete")).toBeInTheDocument();
    expect(screen.queryByText("0/0")).not.toBeInTheDocument();
  });

  it("shows milestone counts for in-progress phases", () => {
    render(
      <PhaseCardMilestones
        milestonesPending={false}
        showCompleteLabel={false}
        completed={2}
        total={5}
        pct={40}
      />,
    );

    expect(screen.getByText("2/5")).toBeInTheDocument();
  });
});
