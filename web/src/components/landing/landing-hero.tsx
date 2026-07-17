import Link from "next/link";

import { HeroTerminalCard } from "@/components/landing/hero-terminal-card";
import { REPO_URL, TRUST_BADGES } from "@/lib/landing-content";

export function LandingHero() {
  return (
    <section id="overview" className="landing-section border-b border-border">
      <div className="landing-inner py-14 sm:py-20">
        <p className="mb-5 font-mono text-xs uppercase tracking-[0.14em] text-foreground-muted">
          <span className="mr-2 inline-block size-1.5 bg-accent align-middle" aria-hidden />
          OPEN SOURCE · AI AGENT INFRASTRUCTURE
        </p>

        <h1 className="max-w-[18ch] font-display text-[length:var(--text-hero)] leading-[0.95] tracking-[-0.03em]">
          The control plane for agents that call{" "}
          <em className="italic">LLMs</em> in production.
        </h1>

        <p className="mt-6 max-w-[52ch] text-lg leading-relaxed text-foreground-muted">
          Intercept every model request. Validate tenant identity. Enforce
          policy. Prepare memory context — at the proxy, not in application glue
          code.
        </p>

        <div className="mt-8 flex flex-wrap items-center gap-3">
          <Link href="/docs/getting-started/introduction" className="btn-solid">
            Read the docs →
          </Link>
          <a
            href={REPO_URL}
            className="btn-outline"
            rel="noopener noreferrer"
            target="_blank"
          >
            View on GitHub
          </a>
        </div>

        <p className="mt-6 font-mono text-xs text-foreground-muted">
          {TRUST_BADGES.join(" · ")}
        </p>

        <div className="mt-12 max-w-3xl">
          <HeroTerminalCard />
        </div>
      </div>
    </section>
  );
}
