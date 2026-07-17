export const REPO_URL = "https://github.com/Rick1330/ibex-harness";

export const SITE_VERSION = "v0.4.2";
export const GITHUB_STARS_STUB = "2.3k";
export const STATUS_STUB = "All systems operational";

export const FEATURES = [
  {
    index: "01",
    tag: "INGRESS_PROXY",
    title: "OpenAI-compatible proxy",
    body: "Drop-in ingress for chat completions. Validate agents and org scope on every request before traffic reaches your model provider.",
  },
  {
    index: "02",
    tag: "TENANT_AUTH",
    title: "Tenant auth + rate limits",
    body: "gRPC auth validation, per-org Redis sliding windows, and defense-in-depth isolation so agents cannot cross tenant boundaries.",
  },
  {
    index: "03",
    tag: "MEMORY_PATH",
    title: "Memory-ready request path",
    body: "Phase 1 ships the proxy and auth foundation. Memory injection, context assembly, and drift detection land on the same ingress.",
  },
  {
    index: "04",
    tag: "TELEMETRY",
    title: "Observable by default",
    body: "Structured logs, Prometheus metrics, and OpenTelemetry traces across proxy boundaries — built for operators running agents at scale.",
  },
] as const;

export const FLOW = [
  {
    step: "01",
    name: "Agent request",
    desc: "Your agent calls the proxy with OpenAI-compatible headers and tenant credentials.",
  },
  {
    step: "02",
    name: "Validate + limit",
    desc: "Auth service verifies the token and agent; Redis enforces per-org rate limits.",
  },
  {
    step: "03",
    name: "Assemble context",
    desc: "Phase 2+ injects memory and directives before the provider call (roadmap).",
  },
  {
    step: "04",
    name: "Forward + trace",
    desc: "The proxy forwards to your LLM provider and records latency, org, and route metrics.",
  },
] as const;

export const STACK_PORTS = [
  { index: "01", label: "Proxy on :8080" },
  { index: "02", label: "Auth gRPC on :50051" },
  { index: "03", label: "Postgres + Redis" },
  { index: "04", label: "OTLP collector" },
] as const;

export const STACK_COMMANDS = [
  "make db-migrate && make db-seed",
  "docker compose -f infra/compose/docker-compose.yml up",
] as const;

export const STACK_LOGS = [
  "ibex-proxy  | Listening on :8080",
  "ibex-auth   | gRPC ready on :50051",
  "postgres    | database system is ready",
  "redis       | Ready to accept connections",
] as const;

export const METRICS = [
  { value: "< 20ms", label: "P99 PROXY BUDGET" },
  { value: "MIT", label: "OPEN SOURCE LICENSE" },
  { value: "RLS", label: "TENANT ISOLATION MODEL" },
  { value: "Go", label: "PROXY + AUTH SERVICES" },
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
    { label: "Roadmap", href: "/roadmap" },
  ],
  community: [
    { label: "GitHub", href: REPO_URL, external: true },
    { label: "Blog", href: "/blog" },
    { label: "Changelog", href: "/releases" },
  ],
  legal: [
    { label: "MIT license", href: `${REPO_URL}/blob/main/LICENSE`, external: true },
    { label: "Security", href: `${REPO_URL}/security`, external: true },
    { label: "Privacy", href: "/llms.txt" },
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

export const TRACE_STEPS = [
  { name: "auth.ValidateAgent (gRPC)", ms: "2.1ms" },
  { name: "ratelimit.Check (Redis)", ms: "0.4ms" },
  { name: "forward to provider", ms: "12.8ms" },
  { name: "200 OK · trace export", ms: "1.1ms" },
] as const;
