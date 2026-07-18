import { cn } from "@/lib/cn";

type WordmarkTextProps = Readonly<{
  size?: "nav" | "footer";
  className?: string;
}>;

/**
 * Formal brand wordmark — “IBEX Harness” (IBEX caps + title-case Harness).
 * Display serif, no casual italic-only lockup.
 */
export function WordmarkText({ size = "nav", className }: WordmarkTextProps) {
  return (
    <span
      className={cn(
        "font-display font-normal tracking-[-0.015em] text-foreground",
        size === "footer" ? "text-[1.25rem]" : "text-[1.125rem] md:text-[1.25rem]",
        className,
      )}
    >
      <span className="tracking-[0.06em]">IBEX</span>
      {"\u00A0"}
      <span>Harness</span>
    </span>
  );
}

type WordmarkProps = Readonly<{
  size?: "nav" | "footer";
}>;

export function Wordmark({ size = "nav" }: WordmarkProps) {
  return <WordmarkText size={size} />;
}
