import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { sampleBenchmarkRun } from "@/lib/benchmarks/test-fixtures";

vi.mock("@/hooks/use-benchmark-data", () => ({
  useBenchmarkData: vi.fn(),
}));

vi.mock("@/components/benchmarks/percentile-chart", () => ({
  PercentileChart: () => <div data-testid="percentile-chart" />,
}));

vi.mock("@/components/benchmarks/throughput-duration-chart", () => ({
  ThroughputDurationChart: () => <div data-testid="throughput-chart" />,
}));

import { BenchmarkLoadPanel } from "@/components/benchmarks/benchmark-load-panel";
import { useBenchmarkData } from "@/hooks/use-benchmark-data";

const mockUseBenchmarkData = vi.mocked(useBenchmarkData);

describe("BenchmarkLoadPanel", () => {
  it("renders empty state when no runs", () => {
    mockUseBenchmarkData.mockReturnValue({
      data: undefined,
      runs: [],
      latest: null,
      isLoading: false,
      isError: false,
      error: null,
      errorMessage: null,
      refresh: vi.fn(),
    });
    render(<BenchmarkLoadPanel />);
    expect(screen.getByRole("heading", { name: "No benchmark runs yet" })).toBeInTheDocument();
  });

  it("renders k6 KPIs for latest run", () => {
    mockUseBenchmarkData.mockReturnValue({
      data: undefined,
      runs: [sampleBenchmarkRun()],
      latest: sampleBenchmarkRun({ k6: { ...sampleBenchmarkRun().k6, p99_ms: 3, req_per_s: 1000 } }),
      isLoading: false,
      isError: false,
      error: null,
      errorMessage: null,
      refresh: vi.fn(),
    });
    render(<BenchmarkLoadPanel />);
    expect(screen.getByLabelText("p99 latency")).toBeInTheDocument();
    expect(screen.getByText("3.00 ms")).toBeInTheDocument();
    expect(screen.getByText(/k6 · 100 VUs/)).toBeInTheDocument();
  });
});
