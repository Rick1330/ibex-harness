import Link from "next/link";

export function LandingCta() {
  return (
    <section
      aria-labelledby="landing-cta-heading"
      className="landing-section border-b border-border"
    >
      <div className="landing-inner py-16 sm:py-24">
        <p className="font-mono text-xs uppercase tracking-[0.14em] text-foreground-muted">
          {"// READY WHEN YOU ARE"}
        </p>
        <h2
          id="landing-cta-heading"
          className="mt-4 max-w-[16ch] font-display text-[length:var(--text-4xl)] leading-[1.05] tracking-[-0.02em]"
        >
          Put agent memory <em className="italic">at the proxy.</em>
        </h2>
        <p className="mt-5 max-w-[48ch] text-base leading-relaxed text-foreground-muted">
          Read the docs, explore benchmarks, and follow the roadmap for memory
          and context assembly.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-3">
          <Link href="/docs/getting-started/introduction" className="btn-solid">
            Get started →
          </Link>
          <Link href="/benchmarks" className="btn-outline">
            View benchmarks
          </Link>
        </div>
      </div>
    </section>
  );
}
