import Link from "next/link";

import { HeroTerminalCard } from "@/components/landing/hero-terminal-card";
import { REPO_URL, SITE_VERSION, TRUST_BADGES } from "@/lib/landing-content";

export function LandingHero() {
  return (
    <section
      id="overview"
      className="mx-auto max-w-[var(--container)] px-5 pb-16 pt-10 sm:px-8 md:pb-24"
    >
      <div className="grid items-center gap-12 lg:grid-cols-12 lg:gap-10">
        <div className="lg:col-span-7">
          <p className="animate-entry mb-5 font-mono text-xs uppercase tracking-[0.14em] text-foreground-muted">
            §01 · CONTROL PLANE
          </p>
          <h1 className="animate-entry font-display text-[clamp(2.75rem,2rem+3vw,4.25rem)] leading-[0.95] tracking-[-0.03em] [animation-delay:60ms]">
            The control plane for agents that call LLMs{" "}
            <em className="not-italic text-foreground">in production.</em>
          </h1>
          <p className="animate-entry mt-6 max-w-[52ch] text-lg leading-relaxed text-foreground-muted [animation-delay:120ms]">
            Open-source OpenAI-compatible proxy. Intercept every model request,
            validate tenant identity, enforce policy, and prepare memory context
            — at the proxy, not in glue code.
          </p>
          <div className="animate-entry mt-8 flex flex-wrap items-center gap-3 [animation-delay:180ms]">
            <Link
              href="/docs/getting-started/introduction"
              className="inline-flex h-10 items-center rounded-sm bg-foreground px-5 text-sm font-medium text-background transition-colors hover:bg-foreground/90"
            >
              Get started
            </Link>
            <Link
              href="/docs/architecture/overview"
              className="inline-flex h-10 items-center rounded-sm border border-border px-5 text-sm font-medium transition-colors hover:border-border-strong hover:bg-surface-1"
            >
              Read the spec →
            </Link>
            <p className="w-full font-mono text-xs text-foreground-subtle sm:w-auto">
              curl -fsSL ibex.sh | sh
            </p>
          </div>
          <p className="animate-entry mt-6 font-mono text-xs text-foreground-muted [animation-delay:220ms]">
            {TRUST_BADGES.join(" · ")}
          </p>
        </div>

        <div className="animate-entry lg:col-span-5 [animation-delay:140ms]">
          <HeroTerminalCard />
        </div>
      </div>
      <p className="sr-only">
        Version {SITE_VERSION}. Repository at{" "}
        <a href={REPO_URL}>{REPO_URL}</a>.
      </p>
    </section>
  );
}
