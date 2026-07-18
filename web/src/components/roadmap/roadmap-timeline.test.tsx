import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RoadmapTimeline } from "@/components/roadmap/roadmap-timeline";

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: Readonly<{
    children: React.ReactNode;
    href: string;
  }>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

afterEach(() => {
  cleanup();
});

describe("RoadmapTimeline", () => {
  it("renders phase titles, status, and milestone links", () => {
    render(
      <RoadmapTimeline
        phases={[
          {
            slug: "phase-1-core-platform",
            anchor: "phase-1-core-platform",
            phaseIndex: "1",
            shortTitle: "Core Platform",
            title: "Phase 1: Core Platform",
            status: "completed",
            completed: 2,
            total: 2,
            bullets: [
              {
                title: "Auth service",
                url: "/roadmap/phase-1-core-platform/milestones/auth",
                status: "completed",
              },
            ],
          },
          {
            slug: "phase-3-memory-engine",
            anchor: "phase-3-memory-engine",
            phaseIndex: "3",
            shortTitle: "Memory Engine",
            title: "Phase 3: Memory Engine",
            status: "planned",
            completed: 0,
            total: 0,
            milestonesPending: true,
            bullets: [],
          },
        ]}
      />,
    );

    expect(screen.getByText("Core Platform")).toBeInTheDocument();
    expect(screen.getByText("shipped")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Auth service/i })).toHaveAttribute(
      "href",
      "/roadmap/phase-1-core-platform/milestones/auth",
    );
    expect(
      screen.getByText(/Goals defined — milestones coming soon/i),
    ).toBeInTheDocument();
  });
});
