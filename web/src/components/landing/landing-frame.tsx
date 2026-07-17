import type { ReactNode } from "react";

import { SITE_VERSION } from "@/lib/landing-content";

type LandingFrameProps = Readonly<{
  children: ReactNode;
}>;

const RAIL_SECTIONS = ["§01", "§02", "§03", "§04"] as const;

/** Page frame: left version rail + full-width landing content. */
export function LandingFrame({ children }: LandingFrameProps) {
  return (
    <div className="ibex-landing relative min-h-screen bg-background pt-[var(--site-nav-height)] text-foreground">
      <aside
        className="landing-rail pointer-events-none absolute bottom-0 left-0 top-[var(--site-nav-height)] z-10 hidden border-r border-border lg:block"
        aria-hidden
      >
        <p className="landing-rail-label font-mono text-[10px] uppercase tracking-[0.18em] text-foreground-subtle">
          IBEX HARNESS · {SITE_VERSION} · PHASE 1
        </p>
        <div className="landing-rail-marks font-mono text-[10px] text-foreground-subtle">
          {RAIL_SECTIONS.map((mark) => (
            <span key={mark}>{mark}</span>
          ))}
        </div>
      </aside>
      <div className="landing-main lg:pl-[3.25rem]">{children}</div>
    </div>
  );
}
