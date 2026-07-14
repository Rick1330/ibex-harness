export const REPO_URL = "https://github.com/Rick1330/ibex-harness";

export const FEATURES = [
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

export const FLOW = [
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

export const METRICS = [
  { value: "<20ms", label: "p99 proxy budget" },
  { value: "MIT", label: "open source license" },
  { value: "RLS", label: "tenant isolation model" },
  { value: "Go", label: "proxy + auth services" },
] as const;

export const MARQUEE = [
  "PROXY",
  "AUTH",
  "RATE-LIMITS",
  "MULTI-TENANT",
  "MEMORY-READY",
  "OPENAI-COMPAT",
  "MIT",
] as const;

export const MARQUEE_TRACKS = ["primary", "duplicate"] as const;

export const STACK_COMMANDS = [
  "make db-migrate && make db-seed",
  "docker compose -f infra/compose/docker-compose.yml up",
  "Proxy on :8080 · Auth gRPC on :50051",
] as const;

export const FOOTER_LINKS = {
  product: [
    { label: "Docs", href: "/docs/getting-started/introduction" },
    { label: "Blog", href: "/blog" },
    { label: "Benchmarks", href: "/benchmarks" },
    { label: "Changelog", href: "/releases" },
    { label: "Roadmap", href: "/roadmap" },
  ],
  project: [
    { label: "GitHub", href: REPO_URL, external: true },
    { label: "llms.txt", href: "/llms.txt" },
    { label: "Sitemap", href: "/sitemap.xml" },
  ],
} as const;
