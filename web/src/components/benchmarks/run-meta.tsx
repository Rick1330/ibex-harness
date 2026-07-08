import type { BenchmarkRun } from "@/lib/benchmarks/types";

type RunMetaProps = Readonly<{
  run: BenchmarkRun;
}>;

function formatTimestamp(value: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toUTCString();
}

export function RunMeta({ run }: RunMetaProps) {
  return (
    <p className="font-mono text-xs text-muted-foreground">
      {run.runner_os} · Go {run.go_version || "—"} · k6 {run.k6_version} · {run.runner_cpu} ·{" "}
      {run.runner_vcpus} vCPU · {run.runner_ram_gb} GB RAM · {formatTimestamp(run.timestamp)}
    </p>
  );
}
