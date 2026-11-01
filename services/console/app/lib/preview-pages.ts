import type { SurfaceKey } from "~~/shared/operator/surfaces"
import { SURFACES } from "~~/shared/operator/surfaces"

export type PreviewBlockKind =
  | "toolbar"
  | "table"
  | "detail"
  | "timeline"
  | "cards"
  | "chart"
  | "form"
  | "split"
  | "matrix"
  | "ledger"
  | "stream"

export type PreviewBlock = {
  title: string
  description: string
  kind: PreviewBlockKind
  rows?: number
}

export type PreviewPageConfig = {
  surfaceKey: SurfaceKey
  label: string
  eyebrow: string
  questions: string[]
  contract: string
  verdict: string
  scope: string
  range: string
  coverage: string
  blocks: PreviewBlock[]
}

type PreviewContext = Pick<PreviewPageConfig, "verdict" | "scope" | "range" | "coverage">

const contexts: Record<Exclude<SurfaceKey, "overview" | "platform" | "explore">, PreviewContext> = {
  incidents: {
    verdict: "Preview renders 9 illustrative incidents. The incident object contract is not connected, so no live count, owner, or severity is claimed.",
    scope: "org_demo_42 · all environments",
    range: "open queue + 14 days",
    coverage: "0% live · illustrative only",
  },
  sessions: {
    verdict: "Preview renders 18 illustrative sessions. Session-to-trace joins and turn-level policy records are not connected.",
    scope: "org_demo_42 · all environments",
    range: "last 24 hours",
    coverage: "0% live · illustrative only",
  },
  agents: {
    verdict: "Preview renders an illustrative agent inventory shell. Agent summary, detail, health, and statistics contracts are not connected.",
    scope: "Current organization · scope not available",
    range: "Top-bar range · not yet applied",
    coverage: "0% live · no agent records",
  },
  memories: {
    verdict: "Preview renders 26 illustrative memories across 9 agents. Content reads, retrieval history, and conflict writes are not connected.",
    scope: "org_demo_42 · all scopes",
    range: "last 48 hours",
    coverage: "0% live · illustrative only",
  },
  evidence: {
    verdict: "Preview renders an illustrative evidence ledger. The certification rollup and relay contract are not connected.",
    scope: "org_demo_42 · all producers",
    range: "last 24 hours",
    coverage: "0% live · illustrative only",
  },
  directives: {
    verdict: "Preview renders illustrative support-triage v14 as a candidate. Promotion, approval, and rollback mutations are not connected.",
    scope: "org_demo_42 · support triage",
    range: "v9 → v14",
    coverage: "0% live · illustrative only",
  },
  policies: {
    verdict: "Preview renders 6 illustrative rules in one snapshot. Run-to-policy provenance and publication writes are not connected.",
    scope: "org_demo_42 · production",
    range: "snapshot 2026-10-27",
    coverage: "0% live · illustrative only",
  },
  drift: {
    verdict: "Preview renders 3 open illustrative drift signals. Baseline certification and acknowledgement writes are not connected.",
    scope: "org_demo_42 · 4 agents",
    range: "last 14 days",
    coverage: "0% live · illustrative only",
  },
  audit: {
    verdict: "Preview renders 12 illustrative audit events. The append-only audit contract and export path are not connected.",
    scope: "org_demo_42 · all actors",
    range: "last 24 hours",
    coverage: "0% live · illustrative only",
  },
  budgets: {
    verdict: "Preview renders 5 illustrative reservations. A certified accounting watermark is not connected, so forecast and remaining values stay illustrative.",
    scope: "org_demo_42 · 5 scopes",
    range: "current billing window",
    coverage: "0% live · illustrative only",
  },
  analytics: {
    verdict: "Preview renders 14 illustrative days. ClickHouse projections are not connected and cannot prove billing, deletion, or audit completeness.",
    scope: "org_demo_42 · all providers",
    range: "last 14 days",
    coverage: "0% live · derived preview only",
  },
  providers: {
    verdict: "Preview renders 6 illustrative provider manifests. Per-provider health and verified capabilities are not connected.",
    scope: "org_demo_42 · 6 providers",
    range: "current manifests",
    coverage: "0% live · illustrative only",
  },
  "mcp-tools": {
    verdict: "Preview renders 12 illustrative tool schemas. Invocation auditing and tool execution are not connected.",
    scope: "org_demo_42 · 6 MCP servers",
    range: "current catalog",
    coverage: "0% live · illustrative only",
  },
  access: {
    verdict: "Preview renders illustrative access data: 4 members, 4 keys, and 3 sessions. AuthService login, MFA, issuance, and revocation are not connected.",
    scope: "org_demo_42 · organization",
    range: "current access state",
    coverage: "0% live · illustrative only",
  },
  settings: {
    verdict: "Preview renders illustrative configuration. No write path, owner attestation, or audit link is connected.",
    scope: "org_demo_42 · organization",
    range: "current configuration",
    coverage: "0% live · illustrative only",
  },
}

const definitions: Record<Exclude<SurfaceKey, "overview" | "platform" | "explore">, {
  eyebrow: string
  questions: string[]
  blocks: PreviewBlock[]
}> = {
  incidents: {
    eyebrow: "Response, not a log",
    questions: [
      "Which incidents are open, and who owns each one?",
      "What changed between acknowledgement and resolution?",
      "Which agent or dependency was affected, and for how long?",
    ],
    blocks: [
      { title: "Open incidents", description: "Severity, owner, age, and state.", kind: "table", rows: 5 },
      { title: "Incident detail", description: "Impact, timeline, ownership, and related runs.", kind: "split" },
      { title: "Response timeline", description: "Acknowledged, mitigated, resolved, and reviewed.", kind: "timeline" },
    ],
  },
  sessions: {
    eyebrow: "A conversation is the unit",
    questions: [
      "What happened across this session, turn by turn?",
      "Which turns produced retrievals, tool calls, and memories?",
      "Where did the session diverge from its expected path?",
    ],
    blocks: [
      { title: "Session list", description: "Owner, last turn, model mix, and outcome.", kind: "table", rows: 5 },
      { title: "Turn timeline", description: "Prompt, retrieval, call, response, and error per turn.", kind: "timeline" },
      { title: "Trajectory and inspector", description: "Session graph beside the selected turn.", kind: "split" },
    ],
  },
  agents: {
    eyebrow: "Behaviour and spend per agent",
    questions: [
      "How many runs did each agent start, and how did they end?",
      "Which agents are close to their budget headroom?",
      "Where has behaviour drifted from the baseline?",
    ],
    blocks: [
      { title: "Agent inventory", description: "Version, model, run rate, error rate, and headroom.", kind: "table", rows: 6 },
      { title: "Agent health and inventory", description: "Rows appear when the tenant-scoped agent summary contract is available.", kind: "table", rows: 0 },
      { title: "Agent detail", description: "Runs, directive linkage, drift state, and cost require agent read contracts.", kind: "detail" },
    ],
  },
  memories: {
    eyebrow: "What was stored, and why",
    questions: [
      "Which memories are active, stale, conflicting, or quarantined?",
      "Which agent stored each memory, and at what confidence?",
      "What was retrieved, pinned, or paused for safety review?",
    ],
    blocks: [
      { title: "Memory index", description: "Content, labels, agent, lifecycle, safety, retrieval, and lineage.", kind: "table", rows: 8 },
      { title: "Safety posture", description: "PII, injection risk, open conflicts, validity, and retrieval gaps.", kind: "ledger" },
      { title: "Agent context", description: "Filter by the agent that wrote each memory.", kind: "split" },
    ],
  },
  evidence: {
    eyebrow: "Certification before assertion",
    questions: [
      "Which records have a certified evidence record?",
      "Which tombstones were written, and why?",
      "Where does the outbox to ClickHouse chain break?",
    ],
    blocks: [
      { title: "Coverage ledger", description: "Counts by tier, component, and capture mode.", kind: "ledger" },
      { title: "Tombstones", description: "Deleted or expired records and their legal basis.", kind: "table", rows: 4 },
      { title: "Evidence chain", description: "Outbox row, producer, consumer, and terminal state.", kind: "stream" },
    ],
  },
  directives: {
    eyebrow: "Instructions have versions",
    questions: [
      "Which version of an instruction is live right now?",
      "What changed between this version and the previous one?",
      "What must be true before this version can be promoted?",
    ],
    blocks: [
      { title: "Version timeline", description: "Draft, promoted, rolled back, and archived.", kind: "timeline" },
      { title: "Section-aware diff", description: "Added, removed, and unchanged instruction sections.", kind: "split" },
      { title: "Promotion checklist", description: "Required checks with pass, fail, and pending states.", kind: "detail" },
    ],
  },
  policies: {
    eyebrow: "The rules in force",
    questions: [
      "Which policy snapshot applied to this run?",
      "What do the rules actually say in readable form?",
      "What changed between snapshots?",
    ],
    blocks: [
      { title: "Snapshot list", description: "Version, scope, effective time, and digest.", kind: "table", rows: 4 },
      { title: "Readable rules", description: "Decision, condition, and effect.", kind: "detail" },
      { title: "Raw snapshot and diff", description: "Canonical JSON alongside the previous version.", kind: "split" },
    ],
  },
  drift: {
    eyebrow: "Change from baseline",
    questions: [
      "Which signals moved outside their baseline band?",
      "When did the drift begin, and what changed nearby?",
      "Which example runs best explain the shift?",
    ],
    blocks: [
      { title: "Drift inbox", description: "Signal, severity, window, and owner.", kind: "table", rows: 5 },
      { title: "Baseline band", description: "Observed values against the certified baseline.", kind: "chart" },
      { title: "Example runs", description: "Representative traces inside and outside the shift.", kind: "detail" },
    ],
  },
  "audit": {
    eyebrow: "One applied effect",
    questions: [
      "Who changed what, and when?",
      "Was the change applied exactly once?",
      "What did the object look like before and after?",
    ],
    blocks: [
      { title: "Audit events", description: "Actor, action, target, result, and time.", kind: "table", rows: 6 },
      { title: "Event detail", description: "Idempotency key, request id, and diff.", kind: "split" },
      { title: "Object history", description: "Every mutation for the selected target.", kind: "timeline" },
    ],
  },
  budgets: {
    eyebrow: "Reserved, committed, remaining",
    questions: [
      "Which reservations are close to their limit?",
      "What is committed, reserved, and still available?",
      "What happens when a reservation expires?",
    ],
    blocks: [
      { title: "Reservation list", description: "Scope, limit, committed, reserved, and headroom.", kind: "table", rows: 5 },
      { title: "Headroom", description: "Reported spend against each reservation.", kind: "chart" },
      { title: "Reservation lifecycle", description: "Created, reserved, committed, released, and expired.", kind: "timeline" },
    ],
  },
  analytics: {
    eyebrow: "Trends, with provenance",
    questions: [
      "Where do spend, tokens, and latency go over time?",
      "Which provider, model, or agent changed most?",
      "Which timestamps are certified and which are estimates?",
    ],
    blocks: [
      { title: "Spend by dimension", description: "Provider, model, or agent across the selected window.", kind: "chart" },
      { title: "Token flow", description: "Input, output, cached, and reasoning tokens.", kind: "chart" },
      { title: "Latency distribution", description: "Proxy overhead, provider time, and context assembly.", kind: "chart" },
    ],
  },
  providers: {
    eyebrow: "Configured, not assumed",
    questions: [
      "Which providers and models are configured?",
      "What limits and capabilities does each model declare?",
      "Which credentials are present, and when do they rotate?",
    ],
    blocks: [
      { title: "Provider manifests", description: "Provider, endpoint, auth type, and health.", kind: "table", rows: 4 },
      { title: "Model capabilities", description: "Context window, modalities, tools, and streaming.", kind: "matrix" },
      { title: "Limits and rotation", description: "Rate limits, quotas, and credential age.", kind: "detail" },
    ],
  },
  "mcp-tools": {
    eyebrow: "Operator tools are capabilities",
    questions: [
      "Which operator tools exist, and what do they do?",
      "Which side effects can each tool cause?",
      "Who may call each tool, and is it idempotent?",
    ],
    blocks: [
      { title: "Tool inventory", description: "Name, side-effect level, idempotency, and status.", kind: "table", rows: 6 },
      { title: "Input schema", description: "Required fields, bounds, and examples.", kind: "detail" },
      { title: "Permission matrix", description: "Role or key scope against each tool.", kind: "matrix" },
    ],
  },
  access: {
    eyebrow: "Keys and members",
    questions: [
      "Which keys exist, and what scopes do they carry?",
      "Who are the members, and what roles do they hold?",
      "Which keys are due for rotation or revocation?",
    ],
    blocks: [
      { title: "Keys", description: "Prefix, scopes, created, last used, and rotation.", kind: "table", rows: 5 },
      { title: "Members and roles", description: "Member, role, status, and last active.", kind: "matrix" },
      { title: "Permission detail", description: "Effective scopes for the selected subject.", kind: "detail" },
    ],
  },
  settings: {
    eyebrow: "Configuration is evidence too",
    questions: [
      "How is this organization configured?",
      "Which environment and retention rules apply?",
      "Which display and notification preferences are set?",
    ],
    blocks: [
      { title: "Organization", description: "Name, slug, region, and plan boundary.", kind: "form" },
      { title: "Environments and retention", description: "Environment labels and retention windows.", kind: "detail" },
      { title: "Display and notifications", description: "Density, time format, and alert routing.", kind: "form" },
    ],
  },
}

export const PREVIEW_PAGES: Record<string, PreviewPageConfig> = Object.fromEntries(
  Object.entries(definitions).map(([key, value]) => {
    const surface = SURFACES[key as SurfaceKey]
    return [
      key,
      {
        surfaceKey: key as SurfaceKey,
        label: surface.label,
        eyebrow: value.eyebrow,
        questions: value.questions,
        contract: surface.contract,
        ...contexts[key as Exclude<SurfaceKey, "overview" | "platform" | "explore">],
        blocks: value.blocks,
      },
    ]
  }),
) as Record<string, PreviewPageConfig>
