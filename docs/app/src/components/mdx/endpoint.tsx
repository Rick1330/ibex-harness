import { cn } from "@/lib/cn";

const METHOD_TONES = {
  GET: "text-info border-info/40",
  POST: "text-success border-success/40",
  PUT: "text-warning border-warning/40",
  DELETE: "text-danger border-danger/40",
  PATCH: "text-warning border-warning/40",
} as const;

export type HttpMethod = keyof typeof METHOD_TONES;

type EndpointProps = Readonly<{
  method: HttpMethod;
  path: string;
  description?: string;
}>;

export function Endpoint({ method, path, description }: EndpointProps) {
  return (
    <div className="my-4 overflow-hidden rounded-md border border-border bg-panel font-mono text-sm">
      <div className="flex flex-wrap items-center gap-3 px-4 py-3">
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
      {description ? (
        <p className="border-t border-border px-4 py-3 text-sm text-text-secondary">
          {description}
        </p>
      ) : null}
    </div>
  );
}
