import Link from "next/link";

import { SITE_VERSION } from "@/lib/landing-content";

export function LandingCta() {
  return (
    <section
      aria-labelledby="landing-cta-heading"
      className="border-y border-border bg-foreground text-background"
    >
      <div className="mx-auto max-w-[var(--container)] px-5 py-16 text-center sm:px-8 md:py-20">
        <p className="font-mono text-xs uppercase tracking-[0.14em] text-background/70">
          §08 · CLOSING
        </p>
        <h2
          id="landing-cta-heading"
          className="mx-auto mt-4 max-w-2xl font-display text-4xl italic leading-tight tracking-[-0.02em]"
        >
          Put agent memory at the proxy.
        </h2>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/docs/getting-started/introduction"
            className="inline-flex h-10 items-center rounded-sm bg-background px-5 text-sm font-medium text-foreground transition-colors hover:bg-background/90"
          >
            Get started
          </Link>
          <Link
            href="/benchmarks"
            className="inline-flex h-10 items-center rounded-sm border border-background/30 px-5 text-sm font-medium transition-colors hover:bg-background/10"
          >
            View benchmarks
          </Link>
        </div>
        <p className="mt-6 font-mono text-xs text-background/70">
          MIT · {SITE_VERSION} · Built for teams shipping agents.
        </p>
      </div>
    </section>
  );
}
