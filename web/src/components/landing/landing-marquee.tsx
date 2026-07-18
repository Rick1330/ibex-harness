import { MARQUEE } from "@/lib/landing-content";

/** Static wrapping tag strip under hero (DESIGN_GUIDE.md §3 / §20 — no load motion). */
export function LandingMarquee() {
  return (
    <div
      className="flex flex-wrap items-center justify-center gap-x-8 gap-y-2 border-b border-border px-4 py-3.5 font-mono text-[11px] uppercase tracking-[0.25em] text-foreground-muted"
      aria-hidden
    >
      {MARQUEE.map((tag) => (
        <span key={tag} className="inline-flex items-center gap-8">
          {tag}
          <span className="text-foreground-subtle">·</span>
        </span>
      ))}
    </div>
  );
}
