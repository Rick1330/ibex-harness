type WordmarkProps = Readonly<{
  size?: "nav" | "footer";
}>;

export function Wordmark({ size = "nav" }: WordmarkProps) {
  const textSize = size === "footer" ? "text-base" : "text-sm";

  return (
    <span
      className={`font-bold uppercase tracking-[0.05em] ${textSize}`}
    >
      <span className="text-text-primary">IBEX</span>
      <span className="text-text-tertiary"> HARNESS</span>
    </span>
  );
}
