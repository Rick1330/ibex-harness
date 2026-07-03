import { SlaGauge } from "@/components/benchmarks/sla-gauge";
import { K6_TARGETS, SLA_TARGETS } from "@/lib/benchmarks/constants";
import { formatPercent } from "@/lib/benchmarks/format";
import type { BenchmarkRun } from "@/lib/benchmarks/types";

type OverviewSlaSectionProps = Readonly<{
  latest: BenchmarkRun;
}>;

export function OverviewSlaSection({ latest }: OverviewSlaSectionProps) {
  return (
    <div className="rounded-md border border-border bg-card p-5 lg:col-span-1">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
        SLA targets
      </h2>
      <div className="space-y-4">
        <SlaGauge label="Proxy overhead p99" value={latest.k6.p99_ms} target={K6_TARGETS.p99_ms} />
        <SlaGauge
          label="Auth LRU hit"
          value={latest.stages.auth_lru_p99_ms}
          target={SLA_TARGETS.auth_lru_hit_p99_ms}
        />
        <SlaGauge
          label="Auth gRPC fallback"
          value={latest.stages.auth_grpc_p99_ms}
          target={SLA_TARGETS.auth_grpc_fallback_p99_ms}
        />
        <SlaGauge
          label="Rate limit"
          value={latest.stages.rate_limit_p99_ms}
          target={SLA_TARGETS.rate_limit_p99_ms}
        />
        <SlaGauge
          label="Directive resolve"
          value={latest.stages.directive_resolve_p99_ms}
          target={SLA_TARGETS.directive_resolve_p99_ms}
        />
        <SlaGauge
          label="Error rate"
          value={latest.k6.error_rate}
          target={K6_TARGETS.error_rate}
          formatValue={formatPercent}
        />
      </div>
    </div>
  );
}
