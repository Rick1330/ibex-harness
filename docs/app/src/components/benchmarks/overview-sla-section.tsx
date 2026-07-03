import { SlaGauge } from "@/components/benchmarks/sla-gauge";
import { K6_TARGETS, SLA_TARGETS } from "@/lib/benchmarks/constants";
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
        <SlaGauge label="Proxy overhead p99" valueMs={latest.k6.p99_ms} targetMs={K6_TARGETS.p99_ms} />
        <SlaGauge
          label="Auth LRU hit"
          valueMs={latest.stages.auth_lru_p99_ms}
          targetMs={SLA_TARGETS.auth_lru_hit_p99_ms}
        />
        <SlaGauge
          label="Auth gRPC fallback"
          valueMs={latest.stages.auth_grpc_p99_ms}
          targetMs={SLA_TARGETS.auth_grpc_fallback_p99_ms}
        />
        <SlaGauge
          label="Rate limit"
          valueMs={latest.stages.rate_limit_p99_ms}
          targetMs={SLA_TARGETS.rate_limit_p99_ms}
        />
        <SlaGauge
          label="Directive resolve"
          valueMs={latest.stages.directive_resolve_p99_ms}
          targetMs={SLA_TARGETS.directive_resolve_p99_ms}
        />
        <SlaGauge
          label="Error rate"
          valueMs={latest.k6.error_rate * 1000}
          targetMs={K6_TARGETS.error_rate * 1000}
        />
      </div>
    </div>
  );
}
