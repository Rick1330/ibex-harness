import { MARQUEE } from "@/lib/landing-content";

function MarqueeTrack({ trackId }: Readonly<{ trackId: string }>) {
  return (
    <span className="flex shrink-0" aria-hidden={trackId === "duplicate"}>
      {MARQUEE.map((word) => (
        <span key={`${trackId}-${word}`} className="mx-6 flex items-center gap-6">
          {word}
          <span className="inline-block w-3 text-center text-accent" aria-hidden>
            ⩗
          </span>
        </span>
      ))}
    </span>
  );
}

export function LandingMarquee() {
  return (
    <div className="overflow-hidden border-y border-border py-3">
      <div className="animate-marquee flex w-max whitespace-nowrap text-xs tracking-widest text-muted-foreground">
        <MarqueeTrack trackId="primary" />
        <MarqueeTrack trackId="duplicate" />
      </div>
    </div>
  );
}
