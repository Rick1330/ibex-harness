import Link from "next/link";

/** Closing CTA — left stack matching reference: eyebrow, H2, lede, side-by-side CTAs. */
export function LandingCta() {
  return (
    <section
      aria-labelledby="landing-cta-heading"
      className="landing-cta border-b border-border"
    >
      <div className="landing-inner landing-cta-inner">
        <p className="landing-eyebrow">{"// READY WHEN YOU ARE"}</p>
        <h2 id="landing-cta-heading" className="landing-h2 landing-cta-title">
          Put agent memory
          <br />
          <em className="italic">at the proxy.</em>
        </h2>
        <p className="landing-lede landing-cta-lede">
          Read the docs, explore benchmarks, and follow the roadmap for memory
          and context assembly.
        </p>
        <div className="landing-cta-actions">
          <Link
            href="/docs/getting-started/introduction"
            className="btn-solid"
          >
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
