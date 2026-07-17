export const REPO_URL = "https://github.com/Rick1330/ibex-harness";

export const SITE_VERSION = "v0.4.2";
export const GITHUB_STARS_STUB = "2.3k";
export const STATUS_STUB = "All systems operational";

export const FEATURES = [
  {
    index: "01",
    title: "Ingress Proxy",
    body: "OpenAI-compatible endpoints on your domain. Drop-in swap for existing agent clients.",
    snippet: "POST /v1/chat/completions",
  },
  {
    index: "02",
    title: "Tenant Auth",
    body: "Per-org keys, JWT claims, and RLS-safe request context on every call.",
    snippet: "auth.ValidateAgent(org_id)",
  },
  {
    index: "03",
    title: "Memory Path",
    body: "Attach retrieved context at the proxy. Redis and pgvector adapters on the roadmap.",
    snippet: "context.assemble(agent_id)",
  },
  {
    index: "04",
    title: "Telemetry",
    body: "OTLP traces, per-tenant cost and latency, and error taxonomy across the proxy path.",
    snippet: "trace_id=7f3a…c21",
  },
] as const;

export const FLOW = [
  {
    step: "01",
    name: "authenticate",
    desc: "JWT claims · org_id · agent_id",
    snippet: `sub: agent-7f3a
org: acme-prod
scope: chat.write`,
  },
  {
    step: "02",
    name: "rate-limit",
    desc: "Redis sliding window · per org",
    snippet: `quota: 120 rpm
remaining: 118
window: 60s`,
  },
  {
    step: "03",
    name: "retrieve memory",
    desc: "Vector top-k · directive injection",
    snippet: `top_k: 8
latency: 4.2ms
hits: 3`,
  },
  {
    step: "04",
    name: "forward upstream",
    desc: "Provider host · trace export",
    snippet: `host: api.openai.com
status: 200
p99: 17ms`,
  },
] as const;

export const BENCHMARKS = [
  { value: "17ms", label: "P99 overhead" },
  { value: "12.4k rps", label: "Throughput" },
  { value: "48 MiB", label: "Memory" },
  { value: "120ms", label: "Cold start" },
] as const;

export const STACK_SERVICES = [
  "Postgres + pgvector",
  "Redis (auth cache + rate limits)",
  "OTLP collector",
  "Ibex proxy + auth (Go)",
  "Admin UI (roadmap)",
] as const;

export const STACK_COMMANDS = [
  "git clone https://github.com/Rick1330/ibex-harness.git",
  "make db-migrate && make db-seed",
  "docker compose -f infra/compose/docker-compose.yml up",
] as const;

export const SPEC_QUOTES = [
  {
    quote:
      "Every data access must satisfy org_id from the verified auth token — never from the request body.",
    href: "/docs/architecture/multi-tenant-security",
    label: "Multi-tenant security",
  },
  {
    quote:
      "The proxy's only external connections are Redis and Auth gRPC — stateless by design in Phase 1.",
    href: "/docs/architecture/overview",
    label: "Architecture overview",
  },
  {
    quote:
      "Full proxy overhead (excluding the LLM) targets under 20ms at p99.",
    href: "/benchmarks",
    label: "Benchmarks",
  },
] as const;

export const TRUST_BADGES = [
  "MIT",
  "Self-hostable",
  "SOC 2 aligned",
  "No vendor lock-in",
] as const;

export const FOOTER_LINKS = {
  product: [
    { label: "Docs", href: "/docs/getting-started/introduction" },
    { label: "Benchmarks", href: "/benchmarks" },
    { label: "Changelog", href: "/releases" },
    { label: "Roadmap", href: "/roadmap" },
  ],
  community: [
    { label: "GitHub", href: REPO_URL, external: true },
    { label: "Blog", href: "/blog" },
  ],
  project: [
    { label: "llms.txt", href: "/llms.txt" },
    { label: "Sitemap", href: "/sitemap.xml" },
  ],
} as const;

type TerminalTone = "default" | "muted" | "accent" | "success";

export type TerminalLinePart = Readonly<{
  text: string;
  tone?: TerminalTone;
}>;

export type TerminalPanel = Readonly<{
  id: "request" | "response" | "trace";
  lines: ReadonlyArray<
    Readonly<{
      text: string;
      parts: ReadonlyArray<TerminalLinePart>;
    }>
  >;
}>;

export const HERO_TERMINAL_PANELS: ReadonlyArray<TerminalPanel> = [
  {
    id: "request",
    lines: [
      {
        text: "POST /v1/chat/completions",
        parts: [
          { text: "POST ", tone: "accent" },
          { text: "/v1/chat/completions", tone: "default" },
        ],
      },
      {
        text: "headers",
        parts: [
          { text: "Authorization: ", tone: "muted" },
          { text: "Bearer ibex_…", tone: "accent" },
        ],
      },
      {
        text: "agent",
        parts: [
          { text: "X-IBEX-Agent-ID: ", tone: "muted" },
          { text: "7f3a9c21-…", tone: "default" },
        ],
      },
    ],
  },
  {
    id: "response",
    lines: [
      {
        text: "status",
        parts: [
          { text: "HTTP/1.1 ", tone: "muted" },
          { text: "200 OK", tone: "success" },
        ],
      },
      {
        text: "body",
        parts: [
          { text: '{ "id": "chatcmpl-…", ', tone: "muted" },
          { text: '"model": "gpt-4o"', tone: "accent" },
          { text: " }", tone: "muted" },
        ],
      },
      {
        text: "latency",
        parts: [
          { text: "x-ibex-latency-ms: ", tone: "muted" },
          { text: "17", tone: "accent" },
        ],
      },
    ],
  },
  {
    id: "trace",
    lines: [
      {
        text: "trace",
        parts: [
          { text: "trace_id=", tone: "muted" },
          { text: "7f3a9c21c21", tone: "default" },
        ],
      },
      {
        text: "spans",
        parts: [
          { text: "auth.ValidateAgent ", tone: "default" },
          { text: "4ms", tone: "accent" },
        ],
      },
      {
        text: "forward",
        parts: [
          { text: "proxy.forward ", tone: "default" },
          { text: "12ms", tone: "accent" },
        ],
      },
    ],
  },
];
