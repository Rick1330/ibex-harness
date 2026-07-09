import { MARQUEE, MARQUEE_TRACKS } from "@/lib/landing-content";

export function LandingMarquee() {
  return (
    <div className="overflow-hidden border-y border-border py-3">
      <div className="animate-marquee flex w-max whitespace-nowrap text-xs tracking-widest text-muted-foreground">
        {MARQUEE_TRACKS.map((track) => (
          <span key={track} className="flex">
            {MARQUEE.map((word) => (
              <span key={`${track}-${word}`} className="mx-6 flex items-center gap-6">
                {word}
                {" "}
                <span className="text-accent" aria-hidden>
                  ⩗
                </span>
              </span>
            ))}
          </span>
        ))}
      </div>
    </div>
  );
}
