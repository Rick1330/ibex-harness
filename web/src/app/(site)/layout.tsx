import type { ReactNode } from "react";

/** Site pages (blog, benchmarks, changelog, roadmap) — Paper/Ink page chrome. */
export default function SiteGroupLayout({ children }: { children: ReactNode }) {
  return (
    <div className="ibex-site-page min-h-[calc(100dvh-var(--topbar-h))] bg-background text-foreground">
      {children}
    </div>
  );
}
