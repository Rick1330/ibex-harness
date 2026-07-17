import Link from "next/link";

import { HeroTerminalCard } from "@/components/landing/hero-terminal-card";
import { TRUST_BADGES } from "@/lib/landing-content";

/** §01 · Hero — 7/5 split, italic on "in production" (design §6). */
export function LandingHero() {
  return (
    <section id="overview" className="landing-section border-b border-border">
      <div className="landing-inner relative py-[clamp(4rem,3rem+4vw,7rem)]">
        <p
          className="pointer-events-none absolute -left-16 top-8 hidden font-mono text-xs uppercase tracking-[0.14em] text-foreground-muted lg:block"
          style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
          aria-hidden
        >
          §01
        </p>

        <div className="grid items-center gap-10 lg:grid-cols-12 lg:gap-10">
          <div className="lg:col-span-7">
            <p className="mb-5 font-mono text-xs uppercase tracking-[0.14em] text-foreground-muted">
              §01 · CONTROL PLANE
            </p>
            <h1 className="max-w-[16ch] font-display text-[length:var(--text-hero)] leading-[0.95] tracking-[-0.03em]">
              The control plane for agents that call LLMs{" "}
              <em className="italic">in production.</em>
            </h1>
            <p className="mt-6 max-w-[52ch] text-lg leading-relaxed text-foreground-muted">
              Open-source OpenAI-compatible proxy. Intercept every model
              request, validate tenant identity, enforce policy, and prepare
              memory context — at the proxy, not in glue code.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link
                href="/docs/getting-started/introduction"
                className="btn-solid"
              >
                Get started
              </Link>
              <Link href="/docs/architecture/overview" className="btn-outline">
                Read the spec →
              </Link>
              <p className="w-full font-mono text-xs text-foreground-subtle sm:w-auto">
                curl -fsSL ibex.sh | sh
              </p>
            </div>
            <p className="mt-6 font-mono text-xs text-foreground-muted">
              {TRUST_BADGES.join(" · ")}
            </p>
          </div>

          <div className="lg:col-span-5">
            <HeroTerminalCard />
          </div>
        </div>
      </div>
    </section>
  );
}
