import { cn } from "@/lib/cn";

export type MermaidAsciiProps = Readonly<{
  ascii?: string;
  source: string;
  caption?: string;
  className?: string;
}>;

function mermaidAccessibleLabel(source: string): string {
  const firstLine = source
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line.length > 0);
  return firstLine
    ? `Mermaid diagram: ${firstLine}`
    : "Mermaid diagram";
}

/** Renders a Mermaid diagram as monospace ASCII art (build-time conversion). */
export function MermaidAscii({
  ascii,
  source,
  caption,
  className,
}: MermaidAsciiProps) {
  const body = ascii ?? source;
  const showFallbackNote = !ascii && source.length > 0;

  return (
    <figure className={cn("mermaid-ascii my-10 not-prose", className)}>
      <span className="sr-only">{mermaidAccessibleLabel(source)}</span>
      <pre
        aria-hidden="true"
        className="overflow-x-auto rounded-md border border-border bg-panel p-4 font-mono text-xs leading-none text-text-primary"
        data-mermaid-ascii
      >
        <code>{body}</code>
      </pre>
      {showFallbackNote ? (
        <p className="mt-2 text-xs text-text-secondary">
          ASCII conversion unavailable; showing Mermaid source.
        </p>
      ) : null}
      {caption ? (
        <figcaption className="mt-3 text-center text-sm text-text-secondary">
          {caption}
        </figcaption>
      ) : null}
    </figure>
  );
}
