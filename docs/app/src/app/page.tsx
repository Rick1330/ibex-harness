import type { Metadata } from "next";
import Link from "next/link";

import { AsciiBackground } from "@/components/landing/ascii-background";
import { IbexVideo } from "@/components/landing/ibex-video";
import { Reveal } from "@/components/landing/reveal";
import { SITE_DESCRIPTION, SITE_URL } from "@/lib/site-seo";

const FEATURES = [
  {
    tag: "[ 01 ]",
    title: "OpenAI-compatible proxy",
    body: "Drop-in ingress for chat completions. Validate agents and org scope on every request before traffic reaches your model provider.",
    art: [".·:·.", ":====:", "·:··:·"],
  },
  {
    tag: "[ 02 ]",
    title: "Tenant auth + rate limits",
    body: "gRPC auth validation, per-org Redis sliding windows, and defense-in-depth isolation so agents cannot cross tenant boundaries.",
    art: ["↻ ↻ ↻", "◇◆◇◆", "→→→→"],
  },
  {
    tag: "[ 03 ]",
    title: "Memory-ready request path",
    body: "Phase 1 ships the proxy and auth foundation. Memory injection, context assembly, and drift detection land on the same ingress.",
    art: ["┌─┬─┐", "│▓│░│", "└─┴─┘"],
  },
  {
    tag: "[ 04 ]",
    title: "Observable by default",
    body: "Structured logs, Prometheus metrics, and OpenTelemetry traces across proxy boundaries — built for operators running agents at scale.",
    art: ["╱╲╱╲", "▚▞▚▞", "╲╱╲╱"],
  },
] as const;

const FLOW = [
  {
    step: "01",
    name: "agent request",
    desc: "Your agent calls the proxy with OpenAI-compatible headers and tenant credentials.",
  },
  {
    step: "02",
    name: "validate + limit",
    desc: "Auth service verifies the token and agent; Redis enforces per-org rate limits.",
  },
  {
    step: "03",
    name: "assemble context",
    desc: "Phase 2+ injects memory and directives before the provider call (roadmap).",
  },
  {
    step: "04",
    name: "forward + trace",
    desc: "The proxy forwards to your LLM provider and records latency, org, and route metrics.",
  },
] as const;

const METRICS = [
  { value: "<20ms", label: "p99 proxy budget" },
  { value: "MIT", label: "open source license" },
  { value: "RLS", label: "tenant isolation model" },
  { value: "Go", label: "proxy + auth services" },
] as const;

const MARQUEE = [
  "PROXY",
  "AUTH",
  "RATE-LIMITS",
  "MULTI-TENANT",
  "MEMORY-READY",
  "OPENAI-COMPAT",
  "MIT",
] as const;

export const metadata: Metadata = {
  title: "IBEX Harness — Agent memory at the proxy",
  description: SITE_DESCRIPTION,
  openGraph: {
    title: "IBEX Harness — Agent memory at the proxy",
    description: SITE_DESCRIPTION,
    type: "website",
    url: SITE_URL,
    images: [
      {
        url: "/brand/android-chrome-512x512.png",
        width: 512,
        height: 512,
        alt: "IBEX Harness",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "IBEX Harness",
    description: SITE_DESCRIPTION,
    images: ["/brand/android-chrome-512x512.png"],
  },
};

const softwareJsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "IBEX Harness",
  applicationCategory: "DeveloperApplication",
  operatingSystem: "Cross-platform",
  description: SITE_DESCRIPTION,
  url: SITE_URL,
  license: "https://github.com/Rick1330/ibex-harness/blob/main/LICENSE",
  isAccessibleForFree: true,
  offers: {
    "@type": "Offer",
    price: "0",
    priceCurrency: "USD",
  },
};

export default function HomePage() {
  return (
    <div className="ibex-landing relative min-h-screen text-foreground pt-[var(--site-nav-height)]">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(softwareJsonLd) }}
      />
      <AsciiBackground />

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
              OPEN SOURCE · AI AGENT INFRASTRUCTURE
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
                href="https://github.com/Rick1330/ibex-harness"
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
              <span className="text-foreground">~ $</span> git clone
              https://github.com/Rick1330/ibex-harness.git
              <span className="caret ml-1">▊</span>
            </p>
          </div>
        </div>
      </section>

      <div className="overflow-hidden border-y border-border py-3">
        <div className="animate-marquee flex w-max whitespace-nowrap text-xs tracking-widest text-muted-foreground">
          {Array.from({ length: 2 }).map((_, repeat) => (
            <span key={repeat} className="flex">
              {MARQUEE.map((word) => (
                <span key={`${repeat}-${word}`} className="mx-6 flex items-center gap-6">
                  {word} <span className="text-accent" aria-hidden>⩗</span>
                </span>
              ))}
            </span>
          ))}
        </div>
      </div>

      <section id="features" className="mx-auto max-w-7xl px-5 py-20 sm:px-8">
        <div className="mb-12 max-w-2xl">
          <p className="mb-3 text-xs tracking-widest text-muted-foreground">
            // CAPABILITIES
          </p>
          <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
            Built for agents that cannot afford silent failure.
          </h2>
        </div>
        <div className="grid gap-px border border-border bg-border sm:grid-cols-2">
          {FEATURES.map((feature, index) => (
            <Reveal key={feature.tag} delay={index * 80}>
              <article className="group h-full bg-paper p-7 transition-colors hover:bg-card">
                <div className="flex items-start justify-between">
                  <span className="text-xs text-muted-foreground">{feature.tag}</span>
                  <pre
                    className="text-[10px] leading-tight text-muted-foreground transition-colors group-hover:text-accent"
                    aria-hidden
                  >
                    {feature.art.join("\n")}
                  </pre>
                </div>
                <h3 className="mt-6 text-lg font-bold">{feature.title}</h3>
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                  {feature.body}
                </p>
              </article>
            </Reveal>
          ))}
        </div>
      </section>

      <section id="flow" className="border-y border-border">
        <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8">
          <div className="mb-12 max-w-2xl">
            <p className="mb-3 text-xs tracking-widest text-muted-foreground">
              // REQUEST PATH
            </p>
            <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
              Every LLM call passes through one gate.
            </h2>
          </div>
          <div className="grid gap-6 md:grid-cols-4">
            {FLOW.map((step) => (
              <div key={step.step} className="relative">
                <div className="mb-4 text-5xl font-extrabold text-border">
                  {step.step}
                </div>
                <p className="font-bold">
                  <span className="text-muted-foreground">{step.step}. </span>
                  {step.name}
                </p>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {step.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="docs" className="mx-auto max-w-7xl px-5 py-20 sm:px-8">
        <div className="grid items-center gap-10 lg:grid-cols-2">
          <div className="max-w-md">
            <p className="mb-3 text-xs tracking-widest text-muted-foreground">
              // LOCAL STACK
            </p>
            <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
              Run the harness on your machine.
            </h2>
            <p className="mt-5 text-sm leading-relaxed text-muted-foreground">
              Clone the monorepo, apply migrations, and bring up the Phase 1
              compose stack for proxy, auth, Postgres, and Redis.
            </p>
            <ul className="mt-6 space-y-2 text-sm">
              {[
                "make db-migrate && make db-seed",
                "docker compose -f infra/compose/docker-compose.yml up",
                "Proxy on :8080 · Auth gRPC on :50051",
              ].map((item) => (
                <li key={item} className="flex items-center gap-2">
                  <span className="text-accent" aria-hidden>
                    ▸
                  </span>{" "}
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <Reveal>
            <div className="ascii-frame overflow-hidden bg-card">
              <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
                <span className="h-2.5 w-2.5 rounded-full bg-destructive/70" />
                <span className="h-2.5 w-2.5 rounded-full bg-accent/70" />
                <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/50" />
                <span className="ml-2 text-[11px] text-muted-foreground">
                  ibex-proxy — request
                </span>
              </div>
              <pre className="overflow-x-auto p-5 text-[12px] leading-relaxed">
                {`POST /v1/chat/completions
X-IBEX-Agent-ID: <uuid>
Authorization: Bearer <token>

→ auth.ValidateAgent (gRPC)
→ ratelimit.Check (Redis)
→ forward to provider
← 200 OK · trace_id=7f3a…c21`}
                <span className="caret">▊</span>
              </pre>
            </div>
          </Reveal>
        </div>
      </section>

      <section id="metrics" className="mx-auto max-w-7xl px-5 py-20 sm:px-8">
        <div className="grid gap-px border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
          {METRICS.map((metric) => (
            <div key={metric.label} className="bg-paper p-8 text-center">
              <div className="text-4xl font-extrabold tracking-tight">
                {metric.value}
              </div>
              <div className="mt-2 text-xs tracking-widest text-muted-foreground">
                {metric.label.toUpperCase()}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 pb-24 sm:px-8">
        <div className="ascii-frame bg-primary px-8 py-16 text-center text-primary-foreground">
          <p className="mb-4 text-xs tracking-widest opacity-70">
            // READY WHEN YOU ARE
          </p>
          <h2 className="mx-auto max-w-xl text-3xl font-extrabold tracking-tight sm:text-4xl">
            Put agent memory at the proxy.
          </h2>
          <p className="mx-auto mt-4 max-w-md text-sm opacity-80">
            Read the docs, explore benchmarks, and follow the roadmap for
            memory and context assembly.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link
              href="/docs/getting-started/introduction"
              className="inline-flex border border-primary-foreground/30 px-5 py-3 text-sm font-bold transition-transform hover:-translate-y-0.5"
            >
              Get started
            </Link>
            <Link
              href="/benchmarks"
              className="inline-flex border border-primary-foreground/30 px-5 py-3 text-sm font-bold transition-transform hover:-translate-y-0.5"
            >
              View benchmarks
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-5 py-8 text-xs text-muted-foreground sm:flex-row sm:px-8">
          <span className="flex items-center gap-2 font-bold text-foreground">
            <span className="text-accent" aria-hidden>
              ⩗
            </span>{" "}
            IBEX HARNESS
          </span>
          <span>Proxy. Auth. Memory-ready.</span>
          <span>© {new Date().getFullYear()} IBEX Harness</span>
        </div>
      </footer>
    </div>
  );
}
