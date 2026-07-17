import { cn } from "@/lib/cn";

type WordmarkTextProps = Readonly<{
  size?: "nav" | "footer";
  className?: string;
}>;

export function WordmarkText({ size = "nav", className }: WordmarkTextProps) {
  const textSize = size === "footer" ? "text-xl" : "text-[20px]";

  return (
    <span
      className={cn(
        "inline-flex items-baseline gap-1.5 tracking-[-0.02em]",
        textSize,
        className,
      )}
    >
      <span className="font-display italic text-foreground">ibex</span>
      <span
        className="size-1 shrink-0 rounded-full bg-accent"
        aria-hidden
      />
      <span className="font-sans font-medium text-foreground">harness</span>
    </span>
  );
}

type WordmarkProps = Readonly<{
  size?: "nav" | "footer";
}>;

export function Wordmark({ size = "nav" }: WordmarkProps) {
  return <WordmarkText size={size} />;
}
