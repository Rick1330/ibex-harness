export const REPO_URL = "https://github.com/Rick1330/ibex-harness";
export const SITE_VERSION = "v0.1";
export const STATUS_STUB = "All systems operational";

export const MARQUEE = [
  "MEMORY",
  "AUTH",
  "RATE-LIMITS",
  "MULTI-TENANT",
  "MOCK-LIVE",
  "DIRECTIVES",
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
    slug: "AGENT_MEMORY",
    title: "Persistent agent memory",
    body: "The product is a memory graph that follows the agent. Extract, rank, and inject prior knowledge on the next call — without changing the application. That engine lands in Phase 3 on this same ingress.",
  },
  {
    index: "02",
    slug: "INGRESS_PROXY",
    title: "The proxy is the injection point",
    body: "An OpenAI-compatible control plane already sits in front of every model request. Identity, policy, directives, and mock/live forwarding ship today so memory has a place to live.",
  },
  {
    index: "03",
    slug: "TENANT_AUTH",
    title: "Tenant auth + rate limits",
    body: "gRPC auth validation, per-org Redis sliding windows, and defense-in-depth isolation so agents cannot cross tenant boundaries.",
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
    body: "Your agent calls the proxy with OpenAI-compatible headers and an org-scoped token — the same path memory will use.",
  },
  {
    step: "02",
    title: "Validate + limit",
    body: "Auth verifies the token and agent. Redis enforces per-org rate limits before work continues.",
  },
  {
    step: "03",
    title: "Context at the ingress",
    body: "Directives and sticky sessions ship today. Memory retrieval and packing join this step in Phase 3 — that is the product.",
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
  { index: "02", label: "Auth gRPC on :9091" },
  { index: "03", label: "Postgres with RLS — Redis for rate limits — ClickHouse traces" },
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
  { k: "comment" as const, t: "bring up the phase-2 stack" },
  {
    k: "prompt" as const,
    t: "git clone https://github.com/Rick1330/ibex-harness.git",
  },
  { k: "prompt" as const, t: "cd ibex-harness && make compose-dev-up" },
  { k: "output" as const, t: "" },
  { k: "output" as const, t: "ibex-proxy   | listening on :8080" },
  { k: "output" as const, t: "ibex-auth    | grpc on :9091" },
  { k: "output" as const, t: "postgres     | ready for connections" },
  { k: "success" as const, t: "redis        | ready ✓" },
  { k: "output" as const, t: "" },
  { k: "prompt" as const, t: "curl -s localhost:8080/health" },
] as const;

export const STACK_SHELL_LINES = [
  { k: "comment" as const, t: "compose the phase-2 stack" },
  { k: "prompt" as const, t: "make db-migrate && make db-seed" },
  {
    k: "prompt" as const,
    t: "make compose-dev-up",
  },
  { k: "output" as const, t: "ibex-proxy  | Listening on :8080" },
  { k: "output" as const, t: "ibex-auth   | grpc on :9091" },
  { k: "output" as const, t: "postgres    | ready for connections" },
  { k: "success" as const, t: "redis       | Ready to accept connections ✓" },
  { k: "comment" as const, t: "Hit the proxy" },
  { k: "prompt" as const, t: "curl -s localhost:8080/health | jq ." },
] as const;

export const FOOTER_LINKS = {
  product: [
    { label: "Docs", href: "/docs" },
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
