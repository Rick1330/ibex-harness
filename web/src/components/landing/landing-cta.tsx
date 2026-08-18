import Link from "next/link";

/** Closing CTA — copy left, actions right on desktop. */
export function LandingCta() {
  return (
    <section
      aria-labelledby="landing-cta-heading"
      className="landing-cta border-b border-border"
    >
      <div className="landing-inner landing-cta-inner">
        <div className="landing-cta-copy">
          <p className="landing-eyebrow">{"// READY WHEN YOU ARE"}</p>
          <h2 id="landing-cta-heading" className="landing-h2 landing-cta-title">
            Start with the ingress.
            <br />
            <em className="italic">Grow into memory.</em>
          </h2>
          <p className="landing-lede landing-cta-lede">
            Run the authenticated control plane today, then follow the Phase 3
            roadmap for extraction, ranking, and injection on every LLM call.
          </p>
        </div>
        <div className="landing-cta-actions">
          <Link
            href="/docs"
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
