import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SuiteStatusBadge } from "@/components/benchmarks/suite-status-badge";
import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";

describe("SuiteStatusBadge", () => {
  it("renders pass status", () => {
    render(
      <SuiteStatusBadge
        status="pass"
        runNumber={12}
        shortSha="abc1234"
        branch="main"
        timestamp="2026-09-04T00:00:00Z"
      />,
    );
    expect(screen.getByText("PASSING")).toBeInTheDocument();
    expect(screen.getByText(/Run #12/)).toBeInTheDocument();
  });
});

describe("BenchmarkEmptyState", () => {
  it("renders custom empty message", () => {
    render(
      <BenchmarkEmptyState
        title="No extraction runs"
        message="Cassette CI has not published yet."
      />,
    );
    expect(screen.getByRole("heading", { name: "No extraction runs" })).toBeInTheDocument();
    expect(screen.getByText(/Cassette CI/)).toBeInTheDocument();
  });
});
