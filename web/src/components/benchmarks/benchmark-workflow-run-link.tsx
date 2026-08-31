import { isSafeBenchmarkRunUrl } from "@/lib/benchmarks/run-url";

type BenchmarkWorkflowRunLinkProps = Readonly<{
  runUrl: string | undefined;
  label?: string;
  className?: string;
}>;

export function BenchmarkWorkflowRunLink({
  runUrl,
  label = "workflow run",
  className = "underline underline-offset-2",
}: BenchmarkWorkflowRunLinkProps) {
  if (!runUrl || !isSafeBenchmarkRunUrl(runUrl)) {
    return null;
  }

  return (
    <a className={className} href={runUrl} target="_blank" rel="noreferrer">
      {label}
    </a>
  );
}
