export const REPO_URL = "https://github.com/Rick1330/ibex-harness";
export const SITE_VERSION = "v0.1";
export const STATUS_STUB = "All systems operational";

export const MARQUEE = [
  "AUTH",
  "RATE-LIMITS",
  "MULTI-TENANT",
  "MEMORY-READY",
  "OPENAI-COMPAT",
  "GRPC",
  "PROMETHEUS",
  "OPENTELEMETRY",
  "GIT",
  "PROXY",
] as const;

export const FEATURES = [
  {
    index: "01",
    slug: "INGRESS_PROXY",
    title: "OpenAI-compatible proxy",
    body: "Drop-in ingress for chat completions. Validate agents and org scope on every request before traffic reaches your model provider.",
  },
  {
    index: "02",
    slug: "TENANT_AUTH",
    title: "Tenant auth + rate limits",
    body: "gRPC auth validation, per-org Redis sliding windows, and defense-in-depth isolation so agents cannot cross tenant boundaries.",
  },
  {
    index: "03",
    slug: "MEMORY_PATH",
    title: "Memory-ready request path",
    body: "Phase 1 ships the proxy and auth foundation. Memory injection, context assembly, and drift detection land on the same ingress.",
  },
  {
    index: "04",
    slug: "TELEMETRY",
    title: "Observable by default",
    body: "Structured logs, Prometheus metrics, and OpenTelemetry traces across proxy boundaries — built for operators running agents at scale.",
  },
] as const;

export const REQUEST_PATH_STEPS = [
  {
    step: "01",
    title: "Agent request",
    body: "Your agent calls the proxy with OpenAI-compatible headers and an org-scoped token.",
  },
  {
    step: "02",
    title: "Validate + limit",
    body: "Auth verifies the token and agent. Redis enforces per-org rate limits before work continues.",
  },
  {
    step: "03",
    title: "Assemble context",
    body: "Phase 2+ injects memory and directives on the same path — no glue code in your agent.",
  },
  {
    step: "04",
    title: "Forward + trace",
    body: "The proxy forwards to your LLM provider and emits a full request trace for operators.",
  },
] as const;

export const BENCHMARKS = [
  { value: "< 20ms", label: "P99 PROXY BUDGET" },
  { value: "MIT", label: "OPEN SOURCE LICENSE" },
  { value: "RLS", label: "TENANT ISOLATION MODEL" },
  { value: "Go", label: "PROXY + AUTH SERVICES" },
] as const;

export const STACK_PORTS = [
  { index: "01", label: "Proxy on :8080" },
  { index: "02", label: "Auth gRPC on :50051" },
  { index: "03", label: "Postgres with RLS — Redis for rate limits" },
  { index: "04", label: "Prometheus + OTel exporters wired" },
] as const;

export const REQUEST_TRACE_SHELL = [
  { k: "comment" as const, t: "inbound request" },
  { k: "prompt" as const, t: "POST /v1/chat/completions" },
  { k: "output" as const, t: "  X-IBEX-Agent-ID: 7f3a9c21-…" },
  { k: "output" as const, t: "  Authorization: Bearer ibex_…" },
  { k: "output" as const, t: "" },
  { k: "comment" as const, t: "pipeline" },
  { k: "output" as const, t: "auth.ValidateAgent (gRPC)      2.1ms" },
  { k: "output" as const, t: "ratelimit.Check (Redis)        0.8ms" },
  { k: "output" as const, t: "proxy.forward (upstream)      12.4ms" },
  { k: "success" as const, t: "✓ status 200 · duration 17.4ms" },
] as const;

export const HERO_SHELL_LINES = [
  { k: "comment" as const, t: "bring up the phase-1 stack" },
  {
    k: "prompt" as const,
    t: "git clone https://github.com/Rick1330/ibex-harness.git",
  },
  { k: "prompt" as const, t: "cd ibex-harness && make up" },
  { k: "output" as const, t: "" },
  { k: "output" as const, t: "ibex-proxy   | listening on :8080" },
  { k: "output" as const, t: "ibex-auth    | grpc on :50051" },
  { k: "output" as const, t: "postgres     | ready for connections" },
  { k: "success" as const, t: "redis        | ready ✓" },
  { k: "output" as const, t: "" },
  { k: "prompt" as const, t: "curl -s localhost:8080/v1/models" },
] as const;

export const STACK_SHELL_LINES = [
  { k: "comment" as const, t: "compose the phase-1 stack" },
  { k: "prompt" as const, t: "make db-migrate && make db-seed" },
  {
    k: "prompt" as const,
    t: "docker compose -f infra/compose/docker-compose.yml up",
  },
  { k: "output" as const, t: "ibex-proxy  | Listening on :8080" },
  { k: "output" as const, t: "ibex-auth   | grpc on :50051" },
  { k: "output" as const, t: "postgres    | ready for connections" },
  { k: "success" as const, t: "redis       | Ready to accept connections ✓" },
  { k: "comment" as const, t: "Hit the proxy" },
  { k: "prompt" as const, t: "curl -s localhost:8080/v1/models | jq ." },
] as const;

export const FOOTER_LINKS = {
  product: [
    { label: "Docs", href: "/docs/getting-started/introduction" },
    { label: "Benchmarks", href: "/benchmarks" },
    { label: "Roadmap", href: "/roadmap" },
  ],
  community: [
    { label: "GitHub", href: REPO_URL, external: true },
    { label: "Blog", href: "/blog" },
    { label: "Changelog", href: "/releases" },
  ],
  legal: [
    {
      label: "MIT license",
      href: `${REPO_URL}/blob/main/LICENSE`,
      external: true,
    },
    { label: "Security", href: `${REPO_URL}/security`, external: true },
    { label: "Privacy", href: "/llms.txt" },
  ],
} as const;
