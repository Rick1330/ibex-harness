import { cn } from "@/lib/cn";

type MermaidPlaceholderProps = Readonly<{ className?: string }>;

export function MermaidPlaceholder({ className }: MermaidPlaceholderProps) {
  return (
    <div
      aria-hidden
      className={cn(
        "mermaid-diagram my-8 min-h-[12rem] rounded-[4px] border border-border bg-panel",
        className,
      )}
    />
  );
}

type MermaidErrorProps = Readonly<{ error: string; className?: string }>;

export function MermaidError({ error, className }: MermaidErrorProps) {
  return (
    <figure className={cn("mermaid-diagram my-10 not-prose", className)}>
      <div className="rounded-[4px] border border-danger/40 bg-panel p-4">
        <p className="mb-1 text-sm font-semibold text-danger">Diagram error</p>
        <pre className="whitespace-pre-wrap font-mono text-xs text-text-secondary">
          {error}
        </pre>
      </div>
    </figure>
  );
}
