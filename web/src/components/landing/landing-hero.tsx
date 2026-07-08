import Link from "next/link";

import { IbexVideo } from "@/components/landing/ibex-video";
import { REPO_URL } from "@/lib/landing-content";

export function LandingHero() {
  return (
    <section id="overview" className="relative mx-auto max-w-7xl px-5 sm:px-8">
      <div className="grid items-center gap-2 pb-16 pt-6 md:grid-cols-2 md:pb-24 md:pt-10">
        <div className="relative order-2 flex items-center justify-center md:order-1 md:justify-start">
          <IbexVideo />
        </div>

        <div className="order-1 md:order-2">
          <p
            className="animate-rise mb-5 inline-flex items-center gap-2 border border-border px-3 py-1 text-[11px] tracking-widest text-muted-foreground"
            style={{ animationDelay: "0ms" }}
          >
            <span className="h-1.5 w-1.5 bg-accent" aria-hidden />
            {" OPEN SOURCE · AI AGENT INFRASTRUCTURE"}
          </p>
          <h1
            className="animate-rise text-4xl font-extrabold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl"
            style={{ animationDelay: "60ms" }}
          >
            The control plane for agents that call{" "}
            <span className="text-outline">LLMs</span> in production.
          </h1>
          <p
            className="animate-rise mt-6 max-w-md text-sm leading-relaxed text-muted-foreground"
            style={{ animationDelay: "120ms" }}
          >
            Intercept every model request. Validate tenant identity. Enforce
            policy. Prepare memory context — at the proxy, not in application
            glue code.
          </p>
          <div
            className="animate-rise mt-8 flex flex-wrap items-center gap-3"
            style={{ animationDelay: "180ms" }}
          >
            <Link
              href="/docs/getting-started/introduction"
              className="ascii-frame bg-primary px-5 py-3 text-sm font-bold text-primary-foreground transition-transform hover:-translate-y-0.5"
            >
              Read the docs
            </Link>
            <a
              href={REPO_URL}
              className="ascii-frame bg-paper px-5 py-3 text-sm font-bold transition-transform hover:-translate-y-0.5"
              rel="noopener noreferrer"
              target="_blank"
            >
              View on GitHub →
            </a>
          </div>
          <p
            className="animate-rise mt-6 text-xs text-muted-foreground"
            style={{ animationDelay: "220ms" }}
          >
            <span className="text-foreground">~ $</span>
            {" git clone https://github.com/Rick1330/ibex-harness.git"}
            <span className="caret ml-1">▊</span>
          </p>
        </div>
      </div>
    </section>
  );
}
