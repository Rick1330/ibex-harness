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
    status: "ROADMAP",
    title: "Persistent agent memory",
    body: "A memory graph that follows the agent across calls. The same ingress that handles auth, directives, and tracing becomes the place where recalled context is injected.",
  },
  {
    index: "02",
    slug: "INGRESS_PROXY",
    status: "LIVE",
    title: "The proxy is the injection point",
    body: "OpenAI-compatible ingress for every chat request. It already applies policy, directives, and forwarding in one place, so memory does not need app-specific glue.",
  },
  {
    index: "03",
    slug: "TENANT_AUTH",
    status: "LIVE",
    title: "Tenant auth + rate limits",
    body: "gRPC auth validation and per-org Redis limits protect the edge. Tenant boundaries are enforced before traffic reaches any model provider.",
  },
  {
    index: "04",
    slug: "TELEMETRY",
    status: "LIVE",
    title: "Observable by default",
    body: "Structured logs, Prometheus metrics, and request traces expose what happened on every call. Operators can inspect latency and behavior without sampling raw prompts.",
  },
] as const;

export const REQUEST_PATH_STEPS = [
  {
    step: "01",
    eyebrow: "Ingress",
    title: "Agent request",
    body: "OpenAI-compatible request enters one org-scoped ingress.",
  },
  {
    step: "02",
    eyebrow: "Control",
    title: "Validate + limit",
    body: "Auth verifies the token and agent; Redis applies per-org limits.",
  },
  {
    step: "03",
    eyebrow: "Context",
    title: "Directives + session context",
    body: "System directives and sticky session state are attached before forwarding.",
  },
  {
    step: "04",
    eyebrow: "Execution",
    title: "Forward + trace",
    body: "The provider call is forwarded and traced with p99 overhead under 20ms.",
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
  { k: "comment" as const, t: "one request, one ingress" },
  { k: "prompt" as const, t: "POST /v1/chat/completions" },
  { k: "output" as const, t: "auth ok · directives applied" },
  { k: "success" as const, t: "✓ upstream 200 · trace 17.4ms" },
] as const;

export const HERO_SHELL_LINES = [
  { k: "comment" as const, t: "what it feels like" },
  { k: "prompt" as const, t: "POST /v1/chat/completions" },
  { k: "output" as const, t: "auth ok · directives attached" },
  { k: "success" as const, t: "✓ 200 in 17.4ms" },
] as const;

export const STACK_SHELL_LINES = [
  { k: "comment" as const, t: "compose the phase-2 stack" },
  {
    k: "prompt" as const,
    t: "git clone https://github.com/Rick1330/ibex-harness.git",
  },
  { k: "prompt" as const, t: "cd ibex-harness" },
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
  { k: "output" as const, t: '{ "status": "ok" }' },
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
