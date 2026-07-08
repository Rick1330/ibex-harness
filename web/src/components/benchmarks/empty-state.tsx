import { BarChart3 } from "lucide-react";

export function BenchmarkEmptyState() {
  return (
    <div className="rounded-md border border-dashed border-border bg-card p-10 text-center">
      <BarChart3 className="mx-auto h-5 w-5 text-muted-foreground" strokeWidth={1.5} aria-hidden />
      <h2 className="mt-4 text-lg font-semibold text-foreground">No benchmark runs yet</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Data appears after the benchmark workflow publishes to main. Run the pipeline locally
        or wait for the next scheduled CI run.
      </p>
    </div>
  );
}
