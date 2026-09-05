import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BenchmarkSuitePanelShell } from "@/components/benchmarks/benchmark-suite-panel-shell";
import { SuiteHistoryTable } from "@/components/benchmarks/suite-history-table";
import { SuiteTrendChart } from "@/components/benchmarks/suite-trend-chart";

vi.mock("@/hooks/use-chart-theme", () => ({
  useChartTheme: () => ({
    foreground: "#000",
    muted: "#666",
    border: "#ccc",
    success: "#0a0",
    danger: "#a00",
    warning: "#a80",
  }),
}));

vi.mock("@/hooks/use-render-plot", () => ({
  useRenderPlot: () => undefined,
}));

describe("suite empty / no-regression behavior", () => {
  it("shell shows extraction empty message for runs: []", () => {
    render(
      <BenchmarkSuitePanelShell
        isLoading={false}
        isError={false}
        errorMessage={null}
        loadErrorLabel="Failed"
        isEmpty
        emptyTitle="No extraction-quality runs yet"
        emptyMessage="No extraction-quality runs published yet. Cassette/smoke CI will fill this suite once eval publishes history."
        onRetry={() => undefined}
      >
        <div>should not render</div>
      </BenchmarkSuitePanelShell>,
    );
    expect(screen.getByRole("heading", { name: /No extraction-quality runs yet/ })).toBeInTheDocument();
    expect(screen.getByText(/Cassette\/smoke CI/)).toBeInTheDocument();
    expect(screen.queryByText("should not render")).not.toBeInTheDocument();
  });

  it("SuiteTrendChart shows empty-range copy when data is empty", () => {
    render(<SuiteTrendChart data={[]} />);
    expect(screen.getByText(/No runs in the selected time range/)).toBeInTheDocument();
  });

  it("SuiteHistoryTable still mounts with zero rows", () => {
    render(
      <SuiteHistoryTable
        rows={[]}
        rowKey={() => "x"}
        getStatus={() => "unknown"}
        getBranch={() => "main"}
        csvFilename="empty.csv"
        columns={[{ header: "Run #", cell: () => "—", csv: () => "" }]}
      />,
    );
    expect(screen.getByText("Run #")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Export CSV/i })).toBeDisabled();
  });
});
