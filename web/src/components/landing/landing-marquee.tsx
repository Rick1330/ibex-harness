import { MARQUEE } from "@/lib/landing-content";

function MarqueeTags({ suffix }: Readonly<{ suffix: string }>) {
  return (
    <>
      {MARQUEE.map((tag) => (
        <span
          key={`${suffix}-${tag}`}
          className="inline-flex items-center gap-8"
        >
          {tag}
          <span className="text-foreground-subtle" aria-hidden>
            ·
          </span>
        </span>
      ))}
    </>
  );
}

/**
 * Tag marquee under hero (DESIGN_GUIDE.md §3 / §20).
 * Sole infinite loop — 50s linear; paused via prefers-reduced-motion.
 */
export function LandingMarquee() {
  return (
    <div
      className="landing-marquee overflow-hidden border-b border-border py-3.5"
      aria-hidden
      data-testid="landing-marquee"
    >
      <div className="marquee-track flex w-max whitespace-nowrap font-mono text-[11px] uppercase tracking-[0.25em] text-foreground-muted">
        <div className="flex items-center gap-x-8 px-4">
          <MarqueeTags suffix="a" />
        </div>
        <div className="flex items-center gap-x-8 px-4">
          <MarqueeTags suffix="b" />
        </div>
      </div>
    </div>
  );
}
