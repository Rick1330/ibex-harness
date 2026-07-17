import Link from "next/link";

import { SITE_VERSION } from "@/lib/landing-content";

/**
 * §08 · Closing CTA — inverted band: foreground bg / background text (design §6).
 * Uses explicit CSS vars so inverted colors always resolve.
 */
export function LandingCta() {
  return (
    <section
      aria-labelledby="landing-cta-heading"
      className="border-y border-border"
      style={{
        background: "var(--foreground)",
        color: "var(--background)",
      }}
    >
      <div className="landing-inner py-[clamp(4rem,3rem+4vw,7rem)] text-center">
        <p
          className="font-mono text-xs uppercase tracking-[0.14em]"
          style={{ color: "color-mix(in oklch, var(--background) 70%, transparent)" }}
        >
          §08 · CLOSING
        </p>
        <h2
          id="landing-cta-heading"
          className="mx-auto mt-4 max-w-2xl font-display text-[length:var(--text-4xl)] italic leading-tight tracking-[-0.02em]"
        >
          Put agent memory at the proxy.
        </h2>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/docs/getting-started/introduction"
            className="inline-flex h-10 items-center rounded-sm px-5 text-sm font-medium"
            style={{
              background: "var(--background)",
              color: "var(--foreground)",
            }}
          >
            Get started
          </Link>
          <Link
            href="/benchmarks"
            className="inline-flex h-10 items-center rounded-sm border px-5 text-sm font-medium"
            style={{
              borderColor: "color-mix(in oklch, var(--background) 30%, transparent)",
              color: "var(--background)",
            }}
          >
            View benchmarks
          </Link>
        </div>
        <p
          className="mt-6 font-mono text-xs"
          style={{ color: "color-mix(in oklch, var(--background) 70%, transparent)" }}
        >
          MIT · {SITE_VERSION} · Built for teams shipping agents.
        </p>
      </div>
    </section>
  );
}
