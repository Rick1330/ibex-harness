const WORKFLOW_URL =
  "https://github.com/Rick1330/ibex-harness/actions/workflows/benchmark.yml";

export function BenchmarkFooter() {
  return (
    <footer className="mt-8 border-t border-border pt-6 text-xs text-muted-foreground">
      <p>
        Data source: <code className="font-mono">/benchmarks/benchmark-data.json</code>
      </p>
      <p className="mt-1">
        <a
          href={WORKFLOW_URL}
          target="_blank"
          rel="noreferrer"
          className="underline-offset-4 hover:text-foreground hover:underline"
        >
          View benchmark workflow
        </a>
      </p>
    </footer>
  );
}
