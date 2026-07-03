import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SlaGauge } from "@/components/benchmarks/sla-gauge";

describe("SlaGauge", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders label and formatted value", () => {
    render(<SlaGauge label="Proxy p99" valueMs={12.5} targetMs={20} />);
    expect(screen.getByText("Proxy p99")).toBeInTheDocument();
    expect(screen.getByText("12.50 ms")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Proxy p99 SLA usage" })).toBeInTheDocument();
  });

  it("shows pass state when under target", () => {
    render(<SlaGauge label="Auth LRU" valueMs={5} targetMs={20} />);
    expect(screen.getByText("Auth LRU")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
  });
});
