import { MARQUEE } from "@/lib/landing-content";

/** Horizontal feature ribbon under hero (design §4 marquee). */
export function LandingMarquee() {
  const track = [...MARQUEE, ...MARQUEE];

  return (
    <div className="overflow-hidden border-b border-border py-3" aria-hidden>
      <div className="marquee-track flex w-max gap-8 whitespace-nowrap font-mono text-xs uppercase tracking-[0.14em] text-foreground-muted">
        {track.map((tag, index) => (
          <span key={`${tag}-${index}`} className="inline-flex items-center gap-8">
            {tag}
            <span className="text-foreground-subtle">∨</span>
          </span>
        ))}
      </div>
    </div>
  );
}
