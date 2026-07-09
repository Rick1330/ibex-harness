import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SlaGauge } from "@/components/benchmarks/sla-gauge";

describe("SlaGauge", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders label and formatted value", () => {
    render(<SlaGauge label="Proxy p99" value={12.5} target={20} />);
    expect(screen.getByText("Proxy p99")).toBeInTheDocument();
    expect(screen.getByText("12.50 ms")).toBeInTheDocument();
    expect(screen.getByLabelText("Proxy p99 SLA usage")).toBeInTheDocument();
  });

  it("shows pass state when under target", () => {
    render(<SlaGauge label="Auth LRU" value={5} target={20} />);
    expect(screen.getByText("Auth LRU")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
  });

  it("reports uncapped percentage to assistive tech when over target", () => {
    render(<SlaGauge label="Proxy p99" value={30} target={20} />);
    const gauge = screen.getByLabelText("Proxy p99 SLA usage");
    expect(gauge).toHaveAttribute("aria-valuenow", "150");
    expect(screen.getByText("150%")).toBeInTheDocument();
  });
});
