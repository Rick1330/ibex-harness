import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BenchmarkStatusBadge } from "@/components/benchmarks/status-badge";
import { sampleBenchmarkRun } from "@/lib/benchmarks/test-fixtures";

describe("BenchmarkStatusBadge", () => {
  it("renders pass status", () => {
    render(<BenchmarkStatusBadge run={sampleBenchmarkRun({ status: "pass", run_number: 42 })} />);
    expect(screen.getByText("PASSING")).toBeInTheDocument();
    expect(screen.getByText(/Run #42/)).toBeInTheDocument();
  });

  it("renders regression delta", () => {
    render(
      <BenchmarkStatusBadge
        run={sampleBenchmarkRun({ status: "regression", regression_vs_baseline_pct: 12.3 })}
      />,
    );
    expect(screen.getByText("REGRESSION")).toBeInTheDocument();
    expect(screen.getByText(/\+12\.3% vs baseline/)).toBeInTheDocument();
  });
});
