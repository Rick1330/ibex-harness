import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { KpiCard } from "@/components/benchmarks/kpi-card";

describe("KpiCard", () => {
  afterEach(() => {
    cleanup();
  });
  it("renders label and value", () => {
    render(<KpiCard label="Proxy p99" value="12.50 ms" />);
    expect(screen.getByLabelText("Proxy p99")).toBeInTheDocument();
    expect(screen.getByText("12.50 ms")).toBeInTheDocument();
  });

  it("shows upward trend for positive delta when higher is better", () => {
    render(<KpiCard label="Throughput" value="900 req/s" deltaPct={5.2} higherIsBetter />);
    expect(screen.getByText(/\+5\.2% vs baseline/)).toBeInTheDocument();
  });

  it("shows downward trend wording when lower is better and delta is negative", () => {
    render(<KpiCard label="Proxy p99" value="12.50 ms" deltaPct={-8.1} />);
    expect(screen.getByText(/-8\.1% vs baseline/)).toBeInTheDocument();
  });

  it("omits trend footer when delta is null", () => {
    render(<KpiCard label="Proxy p99" value="12.50 ms" deltaPct={null} />);
    expect(screen.queryByText(/vs baseline/)).not.toBeInTheDocument();
  });
});
