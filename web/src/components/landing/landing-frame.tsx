import type { ReactNode } from "react";

import { SectionRail } from "@/components/site/section-rail";

type LandingFrameProps = Readonly<{
  children: ReactNode;
}>;

/**
 * Landing layout (DESIGN_GUIDE.md §10 / §12).
 * Section rail is sticky *inside* main, under the top bar.
 */
export function LandingFrame({ children }: LandingFrameProps) {
  return (
    <div className="ibex-landing min-h-screen min-w-0 bg-background text-foreground">
      <main className="relative flex w-full min-w-0">
        <SectionRail />
        <div className="min-w-0 flex-1">{children}</div>
      </main>
    </div>
  );
}
