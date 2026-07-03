import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { KpiCard } from "@/components/benchmarks/kpi-card";

describe("KpiCard", () => {
  it("renders label and value", () => {
    render(<KpiCard label="Proxy p99" value="12.50 ms" />);
    expect(screen.getByLabelText("Proxy p99")).toBeInTheDocument();
    expect(screen.getByText("12.50 ms")).toBeInTheDocument();
  });

  it("shows upward trend for positive delta", () => {
    render(<KpiCard label="Throughput" value="900 req/s" deltaPct={5.2} higherIsBetter />);
    expect(screen.getByText(/\+5\.2% vs baseline/)).toBeInTheDocument();
  });
});
