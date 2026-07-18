import { MARQUEE } from "@/lib/landing-content";

/** Tag marquee under hero — 50s linear (DESIGN_GUIDE.md §3 / §20). */
export function LandingMarquee() {
  const track = [...MARQUEE, ...MARQUEE];

  return (
    <div className="overflow-hidden border-b border-border py-3.5" aria-hidden>
      <div className="marquee-track flex w-max gap-10 whitespace-nowrap font-mono text-[11px] uppercase tracking-[0.25em] text-foreground-muted">
        {track.map((tag, index) => (
          <span key={`${tag}-${index}`} className="inline-flex items-center gap-10">
            {tag}
            <span className="text-foreground-subtle">·</span>
          </span>
        ))}
      </div>
    </div>
  );
}
