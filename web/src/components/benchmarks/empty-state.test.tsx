import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";

describe("BenchmarkEmptyState", () => {
  it("renders empty benchmark message", () => {
    render(<BenchmarkEmptyState />);
    expect(screen.getByRole("heading", { name: "No benchmark runs yet" })).toBeInTheDocument();
    expect(screen.getByText(/Data appears after the benchmark workflow/)).toBeInTheDocument();
  });
});
