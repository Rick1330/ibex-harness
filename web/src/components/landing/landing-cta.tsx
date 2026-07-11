import Link from "next/link";

import { LandingShell } from "@/components/landing/landing-shell";

export function LandingCta() {
  return (
    <section className="mx-auto max-w-7xl px-5 pb-24 sm:px-8">
      <div className="ascii-frame landing-cta-panel px-8 py-16 text-center">
        <p className="mb-4 text-xs tracking-widest text-muted-foreground opacity-80">
          {"// READY WHEN YOU ARE"}
        </p>
        <h2 className="mx-auto max-w-xl text-3xl font-extrabold tracking-tight sm:text-4xl">
          Put agent memory at the proxy.
        </h2>
        <p className="mx-auto mt-4 max-w-md text-sm text-muted-foreground">
          Read the docs, explore benchmarks, and follow the roadmap for memory
          and context assembly.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/docs/getting-started/introduction"
            className="ascii-frame bg-primary px-5 py-3 text-sm font-bold text-primary-foreground transition-transform hover:-translate-y-0.5"
          >
            Get started
          </Link>
          <Link
            href="/benchmarks"
            className="ascii-frame bg-paper px-5 py-3 text-sm font-bold transition-transform hover:-translate-y-0.5"
          >
            View benchmarks
          </Link>
        </div>
        <LandingShell
          surface="inset"
          compact
          className="mx-auto mt-8 max-w-2xl text-left"
        >
          <span className="opacity-70">~ $</span>
          {" git clone https://github.com/Rick1330/ibex-harness.git && make compose-dev-up"}
          <span className="caret">▊</span>
        </LandingShell>
      </div>
    </section>
  );
}
