import type { ReactNode } from "react";

type LandingFrameProps = Readonly<{
  children: ReactNode;
}>;

/** Landing page root — paper background + content gutter for § rail. */
export function LandingFrame({ children }: LandingFrameProps) {
  return (
    <div className="ibex-landing relative min-h-screen bg-background pt-[var(--site-nav-height)] text-foreground">
      <div className="lg:px-16">{children}</div>
    </div>
  );
}
