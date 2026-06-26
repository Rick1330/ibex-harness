import { cn } from "@/lib/cn";

type WordmarkTextProps = Readonly<{
  size?: "nav" | "footer";
  className?: string;
}>;

export function WordmarkText({ size = "nav", className }: WordmarkTextProps) {
  const textSize = size === "footer" ? "text-base" : "text-sm";

  return (
    <span
      className={cn(
        "inline-flex items-baseline gap-0 font-semibold tracking-tight",
        textSize,
        className,
      )}
    >
      <span className="text-foreground">ibex</span>
      <span className="text-muted-foreground">harness</span>
    </span>
  );
}

type WordmarkProps = Readonly<{
  size?: "nav" | "footer";
}>;

export function Wordmark({ size = "nav" }: WordmarkProps) {
  return <WordmarkText size={size} />;
}
