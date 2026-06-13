import { cn } from "@/lib/cn";

const METHOD_TONES = {
  GET: "text-info border-info/40",
  POST: "text-success border-success/40",
  PUT: "text-warning border-warning/40",
  DELETE: "text-danger border-danger/40",
} as const;

export type HttpMethod = keyof typeof METHOD_TONES;

type EndpointProps = {
  method: HttpMethod;
  path: string;
};

export function Endpoint({ method, path }: EndpointProps) {
  return (
    <div className="my-4 flex flex-wrap items-center gap-3 rounded-md border border-border bg-panel px-4 py-3 font-mono text-sm">
      <span
        className={cn(
          "inline-flex h-6 items-center rounded-[4px] border bg-panel px-2",
          "text-[11px] font-medium uppercase tracking-wider",
          METHOD_TONES[method],
        )}
      >
        {method}
      </span>
      <code className="text-text-primary">{path}</code>
    </div>
  );
}
