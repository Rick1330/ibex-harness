import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BenchmarkHistoryPanel } from "@/components/benchmarks/benchmark-history-panel";
import { sampleBenchmarkRun } from "@/lib/benchmarks/test-fixtures";

vi.mock("@/hooks/use-benchmark-data", () => ({
  useBenchmarkData: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

import { useBenchmarkData } from "@/hooks/use-benchmark-data";

const mockUseBenchmarkData = vi.mocked(useBenchmarkData);

describe("BenchmarkHistoryPanel", () => {
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
    render(<BenchmarkHistoryPanel />);
    expect(screen.getByRole("heading", { name: "No benchmark runs yet" })).toBeInTheDocument();
  });

  it("renders history table when runs exist", () => {
    mockUseBenchmarkData.mockReturnValue({
      data: undefined,
      runs: [sampleBenchmarkRun({ short_sha: "bfc0a75", branch: "main" })],
      latest: sampleBenchmarkRun(),
      isLoading: false,
      isError: false,
      error: null,
      errorMessage: null,
      refresh: vi.fn(),
    });
    render(<BenchmarkHistoryPanel />);
    expect(screen.getByRole("link", { name: "bfc0a75" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "main" })).toBeInTheDocument();
  });
});
