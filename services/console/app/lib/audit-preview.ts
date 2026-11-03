import { GOVERN_NOW, formatGovernNumber, formatGovernShortDate, formatGovernStamp } from "./govern-format"

export type AuditActorType = "person" | "service" | "policy" | "system" | "relay" | "api_key"

export type AuditActor = {
  name: string
  type: AuditActorType
  auth: string
}

export type AuditOrigin = "console" | "api" | "policy" | "system" | "relay"
export type AuditResult = "applied" | "rejected" | "retrying" | "dead_lettered"
export type AuditEvidence = "certified" | "sampled" | "partial" | "missing"
export type AuditActionCategory = "Config" | "Access" | "Data" | "Spend" | "Runtime"

export type AuditTargetType =
  | "directive"
  | "policy_snapshot"
  | "policy_rule"
  | "agent"
  | "memory"
  | "session"
  | "api_key"
  | "budget"
  | "provider"
  | "relay"
  | "run"
  | "tool"
  | "workspace"

export type AuditTarget = {
  type: AuditTargetType
  id: string
  name: string
  href?: string | null
}

export type AuditRedaction = {
  field: string
  reason: string
  ruleId: string | null
}

export type AuditRequest = {
  method: string
  route: string
  status: number
  durationMs: number
  headers: string[]
  body: Record<string, unknown> | null
  redactions: AuditRedaction[]
}

export type AuditPolicyDecision = {
  decision: "allow" | "deny" | "require_approval"
  ruleId: string
  ruleRevision: number
  snapshotId: string
}

export type AuditDiff = {
  before: Record<string, unknown>
  after: Record<string, unknown>
  summaries: string[]
}

export type AuditRetryAttempt = {
  at: string
  outcome: string
}

export type AuditRetry = {
  attempts: AuditRetryAttempt[]
  nextAt: string | null
  reason: string
}

export type AuditEvent = {
  id: string
  at: string
  actor: AuditActor
  stepUp: boolean
  action: string
  summary: string
  target: AuditTarget
  origin: AuditOrigin
  result: AuditResult
  evidence: AuditEvidence
  requestId: string
  idempotency: { key: string; effects: number; duplicates: number }
  request: AuditRequest
  policy: AuditPolicyDecision | null
  diff?: AuditDiff
  retry?: AuditRetry
  relatedIds: string[]
}

export const AUDIT_RESULT_LABELS: Record<AuditResult, string> = {
  applied: "Applied",
  rejected: "Rejected",
  retrying: "Retrying",
  dead_lettered: "Dead-lettered",
}

export const AUDIT_EVIDENCE_LABELS: Record<AuditEvidence, string> = {
  certified: "Certified",
  sampled: "Sampled",
  partial: "Partial",
  missing: "Missing",
}

export const AUDIT_ORIGIN_LABELS: Record<AuditOrigin, string> = {
  console: "Console",
  api: "API",
  policy: "Policy engine",
  system: "System",
  relay: "Relay",
}

export const AUDIT_ACTOR_TYPE_LABELS: Record<AuditActorType, string> = {
  person: "Person",
  service: "Service",
  policy: "Policy engine",
  system: "System",
  relay: "Relay",
  api_key: "API key",
}

export const AUDIT_TARGET_TYPE_LABELS: Record<AuditTargetType, string> = {
  directive: "Directive",
  policy_snapshot: "Snapshot",
  policy_rule: "Policy rule",
  agent: "Agent",
  memory: "Memory",
  session: "Session",
  api_key: "API key",
  budget: "Budget",
  provider: "Provider",
  relay: "Webhook relay",
  run: "Run",
  tool: "Tool",
  workspace: "Workspace",
}

export type AuditActionDefinition = {
  category: AuditActionCategory | null
  sentence: string
}

export const AUDIT_ACTIONS: Record<string, AuditActionDefinition> = {
  "directive.promote": { category: "Config", sentence: "Promoted a directive version to live" },
  "directive.rollback": { category: "Config", sentence: "Rolled a directive back to an earlier version" },
  "policy.publish": { category: "Config", sentence: "Published a policy snapshot" },
  "policy.evaluate.allow": { category: "Runtime", sentence: "The policy engine allowed a run" },
  "policy.evaluate.deny": { category: "Runtime", sentence: "The policy engine blocked a run" },
  "agent.create": { category: "Config", sentence: "Created an agent" },
  "agent.pause": { category: "Config", sentence: "Paused an agent" },
  "agent.resume": { category: "Config", sentence: "Resumed an agent" },
  "credential.rotate": { category: "Access", sentence: "Rotated a provider credential" },
  "api_key.create": { category: "Access", sentence: "Created an API key" },
  "api_key.revoke": { category: "Access", sentence: "Revoked an API key" },
  "session.revoke": { category: "Access", sentence: "Revoked a session" },
  "memory.tombstone": { category: "Data", sentence: "Tombstoned memory content past its retention window" },
  "memory.delete": { category: "Data", sentence: "Deleted a memory" },
  "budget.reserve": { category: "Spend", sentence: "Reserved budget for a run" },
  "budget.reservation.expire": { category: "Spend", sentence: "Expired an unused budget reservation" },
  "run.start.rejected": { category: "Runtime", sentence: "Rejected a run at admission" },
  "tool.invoke.denied": { category: "Runtime", sentence: "Denied a tool call" },
  "relay.deliver": { category: "Runtime", sentence: "Delivered an event to an external endpoint" },
  "relay.deliver.failed": { category: "Runtime", sentence: "Delivery to an external endpoint failed" },
}

export function auditAction(verb: string): AuditActionDefinition {
  return AUDIT_ACTIONS[verb] ?? { category: null, sentence: "No description registered" }
}

export function auditActionSentence(verb: string): string {
  return auditAction(verb).sentence
}

const actor = (name: string, type: AuditActorType, auth: string): AuditActor => ({ name, type, auth })

export const AUDIT_ACTORS = {
  mira: actor("Mira Chen", "person", "SSO"),
  jon: actor("Jon Park", "person", "SSO"),
  priya: actor("Priya Nair", "person", "SSO"),
  sam: actor("Sam Okafor", "person", "SSO"),
  deploy: actor("Deploy bot", "service", "Workload identity"),
  retention: actor("Retention worker", "service", "Workload identity"),
  budget: actor("Budget worker", "service", "Workload identity"),
  engine: actor("Policy engine", "policy", "Internal mTLS"),
  relay: actor("Runtime relay", "relay", "mTLS"),
  keyCi: actor("key_ci_3f", "api_key", "API key · CI pipeline"),
}

function request(
  requestId: string,
  method: string,
  route: string,
  status: number,
  durationMs: number,
  body: Record<string, unknown> | null,
  redactions: AuditRedaction[] = [],
  extraHeaders: string[] = [],
): AuditRequest {
  return {
    method,
    route,
    status,
    durationMs,
    headers: ["content-type: application/json", `x-request-id: ${requestId}`, "authorization: [redacted]", ...extraHeaders],
    body,
    redactions,
  }
}

const authRedaction: AuditRedaction = {
  field: "authorization",
  reason: "Credential headers are stripped by the platform before storage.",
  ruleId: null,
}

const piiRedaction: AuditRedaction = {
  field: "source_excerpt",
  reason: "Presidio detected personal data in the source excerpt and replaced it before the audit record was written.",
  ruleId: "content.pii",
}

export const auditEvents: AuditEvent[] = [
  {
    id: "evt_1c4b70",
    at: "2026-10-30T14:51:37.508Z",
    actor: AUDIT_ACTORS.relay,
    stepUp: false,
    action: "relay.deliver",
    summary: "Runtime relay is retrying a delivery to SIEM export",
    target: { type: "relay", id: "rel_siem_export", name: "SIEM export webhook" },
    origin: "relay",
    result: "retrying",
    evidence: "missing",
    requestId: "req_1c4b70",
    idempotency: { key: "idem_1c4b70", effects: 0, duplicates: 0 },
    request: request(
      "req_1c4b70",
      "POST",
      "https://siem.example.com/ingest/ibex",
      503,
      8_000,
      { event: "audit.export.batch", batch: "b_44" },
      [],
      ["x-ibex-delivery: dlv_1c4b70"],
    ),
    policy: null,
    retry: {
      attempts: [{ at: "2026-10-30T14:51:37Z", outcome: "HTTP 503" }],
      nextAt: "2026-10-30T15:15:37Z",
      reason: "HTTP 503; retry 2 of 5 scheduled",
    },
    relatedIds: ["evt_90bd14"],
  },
  {
    id: "evt_7f3a21",
    at: "2026-10-30T14:12:08.120Z",
    actor: AUDIT_ACTORS.mira,
    stepUp: true,
    action: "directive.promote",
    summary: "Mira Chen promoted Support triage from v12 to v13",
    target: { type: "directive", id: "dir_support_triage", name: "Support triage v13" },
    origin: "console",
    result: "applied",
    evidence: "certified",
    requestId: "req_7f3a21",
    idempotency: { key: "idem_7f3a21", effects: 1, duplicates: 0 },
    request: request("req_7f3a21", "POST", "/v1/directives/dir_support_triage/promote", 200, 128, {
      from: "v12",
      to: "v13",
      approval: "none",
    }, [authRedaction]),
    policy: null,
    diff: {
      before: { actor: "jon@ws_42", state: "candidate", live_version: "v12" },
      after: { actor: "jon@ws_42", state: "live", live_version: "v13" },
      summaries: ["State: Candidate → Live", "Live version: v12 → v13"],
    },
    relatedIds: [],
  },
  {
    id: "evt_90bd14",
    at: "2026-10-30T13:58:21.402Z",
    actor: AUDIT_ACTORS.relay,
    stepUp: false,
    action: "relay.deliver.failed",
    summary: "Runtime relay dead-lettered a delivery to Incident bridge",
    target: { type: "relay", id: "rel_incident_bridge", name: "Incident bridge webhook" },
    origin: "relay",
    result: "dead_lettered",
    evidence: "missing",
    requestId: "req_90bd14",
    idempotency: { key: "idem_90bd14", effects: 0, duplicates: 2 },
    request: request(
      "req_90bd14",
      "POST",
      "https://hooks.example.com/incident",
      502,
      10_000,
      { event: "drift.signal.opened", signal: "sig_tool_calls" },
      [],
      ["x-ibex-delivery: dlv_90bd14"],
    ),
    policy: null,
    retry: {
      attempts: [
        { at: "2026-10-30T13:44:02Z", outcome: "Timed out after 10s" },
        { at: "2026-10-30T13:51:11Z", outcome: "HTTP 503" },
        { at: "2026-10-30T13:58:21Z", outcome: "HTTP 502 — dead-lettered" },
      ],
      nextAt: null,
      reason: "The endpoint returned 5xx on 3 attempts over 15 minutes.",
    },
    relatedIds: ["evt_b16f5a", "evt_1c4b70"],
  },
  {
    id: "evt_b16f5a",
    at: "2026-10-30T13:22:40.771Z",
    actor: AUDIT_ACTORS.relay,
    stepUp: false,
    action: "relay.deliver",
    summary: "Runtime relay is retrying a delivery to Incident bridge",
    target: { type: "relay", id: "rel_incident_bridge", name: "Incident bridge webhook" },
    origin: "relay",
    result: "retrying",
    evidence: "missing",
    requestId: "req_b16f5a",
    idempotency: { key: "idem_b16f5a", effects: 0, duplicates: 0 },
    request: request(
      "req_b16f5a",
      "POST",
      "https://hooks.example.com/incident",
      504,
      10_000,
      { event: "drift.signal.opened", signal: "sig_latency_shift" },
      [],
      ["x-ibex-delivery: dlv_b16f5a"],
    ),
    policy: null,
    retry: {
      attempts: [{ at: "2026-10-30T13:22:40Z", outcome: "Timed out after 10s" }],
      nextAt: "2026-10-30T15:16:02Z",
      reason: "Timed out; retry 2 of 5 scheduled",
    },
    relatedIds: ["evt_90bd14", "evt_1c4b70"],
  },
  {
    id: "evt_6c2a05",
    at: "2026-10-30T12:40:17.031Z",
    actor: AUDIT_ACTORS.engine,
    stepUp: false,
    action: "policy.evaluate.deny",
    summary: "The policy engine blocked run run_c1d2e3 under Provider model allowlist",
    target: { type: "run", id: "run_c1d2e3", name: "Run run_c1d2e3" },
    origin: "policy",
    result: "applied",
    evidence: "certified",
    requestId: "req_6c2a05",
    idempotency: { key: "idem_6c2a05", effects: 1, duplicates: 0 },
    request: request("req_6c2a05", "POST", "/internal/policy/evaluate", 200, 7, {
      run_id: "run_c1d2e3",
      model: "claude-sonnet-4",
      rule: "models.allowlist@4",
      decision: "deny",
    }),
    policy: {
      decision: "deny",
      ruleId: "models.allowlist",
      ruleRevision: 4,
      snapshotId: "pol_2026_10_27_03",
    },
    relatedIds: [],
  },
  {
    id: "evt_5b19f4",
    at: "2026-10-30T11:22:40.884Z",
    actor: AUDIT_ACTORS.jon,
    stepUp: true,
    action: "credential.rotate",
    summary: "Jon Park rotated the Anthropic provider credential",
    target: { type: "provider", id: "prov_anthropic", name: "Anthropic · production key" },
    origin: "console",
    result: "applied",
    evidence: "certified",
    requestId: "req_5b19f4",
    idempotency: { key: "idem_5b19f4", effects: 1, duplicates: 0 },
    request: request("req_5b19f4", "POST", "/v1/providers/prov_anthropic/credentials/rotate", 200, 312, {
      provider: "anthropic",
      reason: "Scheduled 90-day rotation",
    }, [authRedaction]),
    policy: null,
    relatedIds: ["evt_83c2e7"],
  },
  {
    id: "evt_39f7d2",
    at: "2026-10-30T09:18:02.150Z",
    actor: AUDIT_ACTORS.retention,
    stepUp: false,
    action: "memory.tombstone",
    summary: "The retention job tombstoned memory mem_7c21f0",
    target: { type: "memory", id: "mem_7c21f0", name: "Memory mem_7c21f0" },
    origin: "system",
    result: "applied",
    evidence: "sampled",
    requestId: "req_39f7d2",
    idempotency: { key: "idem_39f7d2", effects: 1, duplicates: 0 },
    request: request("req_39f7d2", "POST", "/internal/retention/tombstone", 200, 47, {
      cutoff_days: 30,
      tombstoned: 2,
    }),
    policy: null,
    relatedIds: ["evt_61a0c5"],
  },
  {
    id: "evt_28e6c1",
    at: "2026-10-30T08:04:55.607Z",
    actor: AUDIT_ACTORS.priya,
    stepUp: true,
    action: "api_key.revoke",
    summary: "Priya Nair revoked API key key_ops_91",
    target: { type: "api_key", id: "key_ops_91", name: "key_ops_91" },
    origin: "console",
    result: "applied",
    evidence: "partial",
    requestId: "req_28e6c1",
    idempotency: { key: "idem_28e6c1", effects: 1, duplicates: 0 },
    request: request("req_28e6c1", "DELETE", "/v1/api-keys/key_ops_91", 200, 96, {
      reason: "Operator left the workspace",
    }, [authRedaction]),
    policy: null,
    relatedIds: [],
  },
  {
    id: "evt_17d5b0",
    at: "2026-10-30T06:31:19.922Z",
    actor: AUDIT_ACTORS.engine,
    stepUp: false,
    action: "run.start.rejected",
    summary: "The policy engine rejected run run_55ac02 under Budget ceiling",
    target: { type: "run", id: "run_55ac02", name: "Run run_55ac02" },
    origin: "policy",
    result: "rejected",
    evidence: "certified",
    requestId: "req_17d5b0",
    idempotency: { key: "idem_17d5b0", effects: 0, duplicates: 0 },
    request: request("req_17d5b0", "POST", "/internal/policy/evaluate", 200, 5, {
      run_id: "run_55ac02",
      rule: "budget.ceiling@3",
      reserved_usd: 1082,
      limit_usd: 1000,
      decision: "deny",
    }),
    policy: {
      decision: "deny",
      ruleId: "budget.ceiling",
      ruleRevision: 3,
      snapshotId: "pol_2026_10_27_03",
    },
    relatedIds: ["evt_72b1d6", "evt_06c4af"],
  },
  {
    id: "evt_06c4af",
    at: "2026-10-30T03:12:44.318Z",
    actor: AUDIT_ACTORS.budget,
    stepUp: false,
    action: "budget.reservation.expire",
    summary: "The budget worker expired an unused $12.40 reservation",
    target: { type: "budget", id: "bud_workspace", name: "Workspace monthly budget" },
    origin: "system",
    result: "applied",
    evidence: "certified",
    requestId: "req_06c4af",
    idempotency: { key: "idem_06c4af", effects: 1, duplicates: 0 },
    request: request("req_06c4af", "POST", "/internal/budgets/expire", 200, 18, {
      reservation: "res_4d10",
      amount_usd: 12.4,
    }),
    policy: null,
    relatedIds: ["evt_4f7ea3"],
  },
  {
    id: "evt_f5b39e",
    at: "2026-10-29T22:47:10.226Z",
    actor: AUDIT_ACTORS.jon,
    stepUp: false,
    action: "agent.pause",
    summary: "Jon Park paused agent Billing assistant",
    target: { type: "agent", id: "ag_billing_analyst", name: "Billing assistant" },
    origin: "console",
    result: "applied",
    evidence: "certified",
    requestId: "req_f5b39e",
    idempotency: { key: "idem_f5b39e", effects: 1, duplicates: 0 },
    request: request("req_f5b39e", "POST", "/v1/agents/ag_billing_analyst/pause", 200, 74, {
      reason: "Elevated tool error rate",
    }, [authRedaction]),
    policy: null,
    relatedIds: ["evt_a05e49"],
  },
  {
    id: "evt_e4a28d",
    at: "2026-10-29T19:05:33.490Z",
    actor: AUDIT_ACTORS.engine,
    stepUp: false,
    action: "tool.invoke.denied",
    summary: "The policy engine denied refund.issue because no approval was recorded",
    target: { type: "tool", id: "tool_refund_issue", name: "refund.issue" },
    origin: "policy",
    result: "rejected",
    evidence: "certified",
    requestId: "req_e4a28d",
    idempotency: { key: "idem_e4a28d", effects: 0, duplicates: 0 },
    request: request("req_e4a28d", "POST", "/internal/policy/evaluate", 200, 6, {
      tool: "refund.issue",
      amount_usd: 310,
      run_id: "run_2c81a4",
      approval: "none",
      rule: "tools.approval@5",
    }),
    policy: {
      decision: "require_approval",
      ruleId: "tools.approval",
      ruleRevision: 5,
      snapshotId: "pol_2026_10_27_03",
    },
    relatedIds: [],
  },
  {
    id: "evt_d3917c",
    at: "2026-10-29T16:05:12.113Z",
    actor: AUDIT_ACTORS.jon,
    stepUp: true,
    action: "directive.rollback",
    summary: "Jon Park rolled Support triage back to v12",
    target: { type: "directive", id: "dir_support_triage", name: "Support triage v12" },
    origin: "console",
    result: "applied",
    evidence: "certified",
    requestId: "req_d3917c",
    idempotency: { key: "idem_d3917c", effects: 1, duplicates: 0 },
    request: request("req_d3917c", "POST", "/v1/directives/dir_support_triage/rollback", 200, 140, {
      from: "v13",
      to: "v12",
      reason: "Refund path regression",
    }, [authRedaction]),
    policy: null,
    diff: {
      before: { live_version: "v13" },
      after: { live_version: "v12" },
      summaries: ["Live version: v13 → v12"],
    },
    relatedIds: ["evt_7f3a21"],
  },
  {
    id: "evt_c2806b",
    at: "2026-10-29T15:40:08.652Z",
    actor: AUDIT_ACTORS.jon,
    stepUp: false,
    action: "memory.delete",
    summary: "Jon Park's delete of memory mem_44b1e2 was rejected by a legal hold",
    target: { type: "memory", id: "mem_44b1e2", name: "Memory mem_44b1e2" },
    origin: "console",
    result: "rejected",
    evidence: "partial",
    requestId: "req_c2806b",
    idempotency: { key: "idem_c2806b", effects: 0, duplicates: 0 },
    request: request("req_c2806b", "DELETE", "/v1/memories/mem_44b1e2", 409, 88, {
      memory_id: "mem_44b1e2",
      hold: "legal_hold_88",
    }, [authRedaction]),
    policy: {
      decision: "deny",
      ruleId: "data.retention",
      ruleRevision: 7,
      snapshotId: "pol_2026_10_27_03",
    },
    relatedIds: ["evt_61a0c5"],
  },
  {
    id: "evt_a05e49",
    at: "2026-10-29T11:02:37.019Z",
    actor: AUDIT_ACTORS.priya,
    stepUp: false,
    action: "agent.resume",
    summary: "Priya Nair resumed agent Billing assistant",
    target: { type: "agent", id: "ag_billing_analyst", name: "Billing assistant" },
    origin: "console",
    result: "applied",
    evidence: "certified",
    requestId: "req_a05e49",
    idempotency: { key: "idem_a05e49", effects: 1, duplicates: 0 },
    request: request("req_a05e49", "POST", "/v1/agents/ag_billing_analyst/resume", 200, 69, {
      note: "Provider failover recovered",
    }, [authRedaction]),
    policy: null,
    relatedIds: ["evt_f5b39e"],
  },
  {
    id: "evt_94d3f8",
    at: "2026-10-29T09:44:02.337Z",
    actor: AUDIT_ACTORS.priya,
    stepUp: true,
    action: "api_key.create",
    summary: "Priya Nair created API key key_ci_3f for CI",
    target: { type: "api_key", id: "key_ci_3f", name: "key_ci_3f" },
    origin: "console",
    result: "applied",
    evidence: "certified",
    requestId: "req_94d3f8",
    idempotency: { key: "idem_94d3f8", effects: 1, duplicates: 0 },
    request: request("req_94d3f8", "POST", "/v1/api-keys", 201, 84, {
      scopes: ["runs:read", "traces:read"],
      owner: "CI pipeline",
    }, [authRedaction]),
    policy: null,
    relatedIds: [],
  },
  {
    id: "evt_83c2e7",
    at: "2026-10-29T08:15:56.044Z",
    actor: AUDIT_ACTORS.jon,
    stepUp: true,
    action: "credential.rotate",
    summary: "Jon Park rotated the Anthropic provider credential",
    target: { type: "provider", id: "prov_anthropic", name: "Anthropic · production key" },
    origin: "console",
    result: "applied",
    evidence: "certified",
    requestId: "req_83c2e7",
    idempotency: { key: "idem_83c2e7", effects: 1, duplicates: 0 },
    request: request("req_83c2e7", "POST", "/v1/providers/prov_anthropic/credentials/rotate", 200, 298, {
      provider: "anthropic",
      reason: "Suspected key exposure",
    }, [authRedaction]),
    policy: null,
    relatedIds: ["evt_5b19f4"],
  },
  {
    id: "evt_72b1d6",
    at: "2026-10-28T21:30:25.771Z",
    actor: AUDIT_ACTORS.engine,
    stepUp: false,
    action: "policy.evaluate.deny",
    summary: "The policy engine blocked run run_1d9f44 under Budget ceiling",
    target: { type: "run", id: "run_1d9f44", name: "Run run_1d9f44" },
    origin: "policy",
    result: "applied",
    evidence: "certified",
    requestId: "req_72b1d6",
    idempotency: { key: "idem_72b1d6", effects: 1, duplicates: 0 },
    request: request("req_72b1d6", "POST", "/internal/policy/evaluate", 200, 5, {
      run_id: "run_1d9f44",
      rule: "budget.ceiling@3",
      decision: "deny",
    }),
    policy: {
      decision: "deny",
      ruleId: "budget.ceiling",
      ruleRevision: 3,
      snapshotId: "pol_2026_10_27_03",
    },
    relatedIds: ["evt_17d5b0"],
  },
  {
    id: "evt_61a0c5",
    at: "2026-10-28T18:12:09.215Z",
    actor: AUDIT_ACTORS.retention,
    stepUp: false,
    action: "memory.tombstone",
    summary: "The retention job tombstoned memory mem_9ab3c2",
    target: { type: "memory", id: "mem_9ab3c2", name: "Memory mem_9ab3c2" },
    origin: "system",
    result: "applied",
    evidence: "sampled",
    requestId: "req_61a0c5",
    idempotency: { key: "idem_61a0c5", effects: 1, duplicates: 0 },
    request: request("req_61a0c5", "POST", "/internal/retention/tombstone", 200, 51, {
      cutoff_days: 30,
      tombstoned: 1,
      pii_redacted: true,
    }, [piiRedaction]),
    policy: null,
    relatedIds: ["evt_c2806b"],
  },
  {
    id: "evt_508fb4",
    at: "2026-10-28T14:55:31.803Z",
    actor: AUDIT_ACTORS.mira,
    stepUp: false,
    action: "directive.promote",
    summary: "Mira Chen's promotion of Billing assistant v9 was rejected",
    target: { type: "directive", id: "dir_billing_assistant", name: "Billing assistant v9" },
    origin: "console",
    result: "rejected",
    evidence: "missing",
    requestId: "req_508fb4",
    idempotency: { key: "idem_508fb4", effects: 0, duplicates: 0 },
    request: request("req_508fb4", "POST", "/v1/directives/dir_billing_assistant/promote", 409, 64, {
      from: "v8",
      to: "v9",
      blocked_by: "models.allowlist@4",
    }, [authRedaction]),
    policy: {
      decision: "deny",
      ruleId: "models.allowlist",
      ruleRevision: 4,
      snapshotId: "pol_2026_10_27_03",
    },
    relatedIds: ["evt_6c2a05"],
  },
  {
    id: "evt_4f7ea3",
    at: "2026-10-28T10:20:14.590Z",
    actor: AUDIT_ACTORS.deploy,
    stepUp: false,
    action: "budget.reserve",
    summary: "Deploy bot reserved $42.00 for run run_77b031",
    target: { type: "budget", id: "bud_workspace", name: "Workspace monthly budget" },
    origin: "api",
    result: "applied",
    evidence: "sampled",
    requestId: "req_4f7ea3",
    idempotency: { key: "idem_4f7ea3", effects: 1, duplicates: 0 },
    request: request("req_4f7ea3", "POST", "/v1/budgets/reservations", 201, 132, {
      run_id: "run_77b031",
      amount_usd: 42,
    }, [authRedaction]),
    policy: null,
    relatedIds: ["evt_06c4af"],
  },
  {
    id: "evt_3e6d92",
    at: "2026-10-28T08:05:47.412Z",
    actor: AUDIT_ACTORS.sam,
    stepUp: false,
    action: "session.revoke",
    summary: "Sam Okafor revoked session sess_3fa8",
    target: { type: "session", id: "sess_3fa8", name: "Session sess_3fa8" },
    origin: "console",
    result: "applied",
    evidence: "certified",
    requestId: "req_3e6d92",
    idempotency: { key: "idem_3e6d92", effects: 1, duplicates: 0 },
    request: request("req_3e6d92", "DELETE", "/v1/sessions/sess_3fa8", 200, 58, {
      reason: "Lost laptop",
    }, [authRedaction]),
    policy: null,
    relatedIds: [],
  },
  {
    id: "evt_2d5c81",
    at: "2026-10-28T06:48:03.960Z",
    actor: AUDIT_ACTORS.priya,
    stepUp: false,
    action: "agent.create",
    summary: "Priya Nair created agent Escalation router",
    target: { type: "agent", id: "ag_escalation_router", name: "Escalation router" },
    origin: "console",
    result: "applied",
    evidence: "certified",
    requestId: "req_2d5c81",
    idempotency: { key: "idem_2d5c81", effects: 1, duplicates: 0 },
    request: request("req_2d5c81", "POST", "/v1/agents", 201, 205, {
      name: "Escalation router",
      model: "balanced-medium",
    }, [authRedaction]),
    policy: null,
    relatedIds: [],
  },
  {
    id: "evt_4a08e3",
    at: "2026-10-27T03:00:00.000Z",
    actor: AUDIT_ACTORS.priya,
    stepUp: false,
    action: "policy.publish",
    summary: "Priya Nair published policy snapshot pol_2026_10_27_03",
    target: { type: "policy_snapshot", id: "pol_2026_10_27_03", name: "Snapshot pol_2026_10_27_03" },
    origin: "console",
    result: "applied",
    evidence: "certified",
    requestId: "req_4a08e3",
    idempotency: { key: "idem_4a08e3", effects: 1, duplicates: 0 },
    request: request("req_4a08e3", "POST", "/v1/policies/snapshots/publish", 200, 176, {
      snapshot: "pol_2026_10_27_03",
      rules: 6,
    }, [authRedaction]),
    policy: null,
    relatedIds: [],
  },
]

export function auditEventById(eventId: string | null | undefined): AuditEvent | null {
  if (!eventId) return null
  return auditEvents.find((event) => event.id === eventId) ?? null
}

export function auditOriginLabel(origin: AuditOrigin): string {
  return AUDIT_ORIGIN_LABELS[origin]
}

export function auditActorSubline(event: AuditEvent): string {
  const label = AUDIT_ACTOR_TYPE_LABELS[event.actor.type]
  return event.stepUp ? `${label} · step-up` : label
}

export function auditActorAuth(event: AuditEvent): string {
  return event.stepUp ? `${event.actor.auth} + WebAuthn step-up` : event.actor.auth
}

export type AuditSavedViewId =
  | "all"
  | "attention"
  | "rejected"
  | "privileged"
  | "config"
  | "credentials"
  | "deletion"
  | "mine"

export const AUDIT_SAVED_VIEWS: { id: AuditSavedViewId; label: string }[] = [
  { id: "all", label: "All events" },
  { id: "attention", label: "Needs attention" },
  { id: "rejected", label: "Rejected" },
  { id: "privileged", label: "Privileged actions" },
  { id: "config", label: "Configuration changes" },
  { id: "credentials", label: "Credentials & keys" },
  { id: "deletion", label: "Data deletion" },
  { id: "mine", label: "By me" },
]

export function auditSavedViewLabel(view: AuditSavedViewId): string {
  return AUDIT_SAVED_VIEWS.find((entry) => entry.id === view)?.label ?? "All events"
}

export function auditMatchesView(event: AuditEvent, view: AuditSavedViewId): boolean {
  switch (view) {
    case "all":
      return true
    case "attention":
      return event.result === "retrying" || event.result === "dead_lettered"
    case "rejected":
      return event.result === "rejected"
    case "privileged":
      return event.stepUp
    case "config":
      return ["directive.", "policy.", "agent."].some((prefix) => event.action.startsWith(prefix))
    case "credentials":
      return ["api_key.", "provider.credential.", "credential."].some((prefix) => event.action.startsWith(prefix))
    case "deletion":
      return event.action === "memory.tombstone" || event.action.endsWith(".delete")
    case "mine":
      return event.actor.name === "Jon Park"
  }
}

export const AUDIT_RANGES = ["1h", "6h", "24h", "7d"] as const
export type AuditRange = (typeof AUDIT_RANGES)[number]

export const AUDIT_RANGE_LABELS: Record<AuditRange, string> = {
  "1h": "Last hour",
  "6h": "Last 6 hours",
  "24h": "Last 24 hours",
  "7d": "Last 7 days",
}

const RANGE_HOURS: Record<AuditRange, number> = { "1h": 1, "6h": 6, "24h": 24, "7d": 168 }

export function auditRangeCutoff(range: AuditRange, now = GOVERN_NOW): string {
  return new Date(now - RANGE_HOURS[range] * 3_600_000).toISOString()
}

export function auditRangeEvents(range: AuditRange, events: AuditEvent[] = auditEvents): AuditEvent[] {
  const cutoff = Date.parse(auditRangeCutoff(range))
  return events.filter((event) => Date.parse(event.at) >= cutoff)
}

export type AuditParsedQuery = {
  text: string
  actor: string | null
  action: string | null
  target: string | null
  result: AuditResult | null
  origin: AuditOrigin | null
  stepUp: boolean | null
}

function stripQuotes(value: string): string {
  return value.replace(/^"(.*)"$/, "$1")
}

export function auditQueryTokens(input: string): string[] {
  const tokens: string[] = []
  let current = ""
  let quoted = false
  for (const character of input) {
    if (character === "\"") {
      quoted = !quoted
      current += character
      continue
    }
    if (!quoted && /\s/.test(character)) {
      if (current) tokens.push(current)
      current = ""
      continue
    }
    current += character
  }
  if (current) tokens.push(current)
  return tokens
}

export function parseAuditQuery(input: string): AuditParsedQuery {
  const parsed: AuditParsedQuery = {
    text: "",
    actor: null,
    action: null,
    target: null,
    result: null,
    origin: null,
    stepUp: null,
  }
  const free: string[] = []

  for (const token of auditQueryTokens(input)) {
    const separator = token.indexOf(":")
    if (separator <= 0) {
      free.push(stripQuotes(token))
      continue
    }
    const key = token.slice(0, separator).toLowerCase()
    const value = stripQuotes(token.slice(separator + 1)).trim()
    if (!value) {
      free.push(token)
      continue
    }
    if (key === "actor") {
      parsed.actor = value.toLowerCase() === "me" ? "Jon Park" : value
    } else if (key === "action") {
      parsed.action = value
    } else if (key === "target") {
      parsed.target = value
    } else if (key === "result") {
      const normalized = value.toLowerCase().replace(/-/g, "_")
      if (normalized in AUDIT_RESULT_LABELS) parsed.result = normalized as AuditResult
      else free.push(token)
    } else if (key === "origin") {
      const normalized = value.toLowerCase()
      if (normalized in AUDIT_ORIGIN_LABELS) parsed.origin = normalized as AuditOrigin
      else free.push(token)
    } else if (key === "step_up" || key === "stepup") {
      if (value === "true") parsed.stepUp = true
      else if (value === "false") parsed.stepUp = false
      else free.push(token)
    } else {
      free.push(token)
    }
  }

  parsed.text = free.join(" ").trim()
  return parsed
}

function normalizedIncludes(haystack: string, needle: string): boolean {
  const normalized = haystack.toLowerCase()
  const query = needle.toLowerCase()
  if (normalized.includes(query)) return true
  const parts = query.split(/[-_\s]+/).filter(Boolean)
  if (parts.length < 2) return false
  const flattened = normalized.replace(/[-_]+/g, " ")
  return parts.every((part) => flattened.includes(part))
}

function actionMatches(action: string, pattern: string): boolean {
  const target = pattern.toLowerCase()
  if (target.endsWith("*")) return action.toLowerCase().startsWith(target.slice(0, -1))
  return action.toLowerCase() === target || action.toLowerCase().startsWith(`${target}.`)
}

function matchesParsedQuery(event: AuditEvent, query: AuditParsedQuery): boolean {
  if (query.actor && !normalizedIncludes(event.actor.name, query.actor)) return false
  if (query.action && !actionMatches(event.action, query.action)) return false
  if (query.target && !normalizedIncludes(`${event.target.name} ${event.target.id}`, query.target)) return false
  if (query.result && event.result !== query.result) return false
  if (query.origin && event.origin !== query.origin) return false
  if (query.stepUp !== null && event.stepUp !== query.stepUp) return false
  if (!query.text) return true
  const haystack = [
    event.summary,
    event.action,
    event.actor.name,
    AUDIT_ACTOR_TYPE_LABELS[event.actor.type],
    event.target.name,
    event.target.id,
    AUDIT_RESULT_LABELS[event.result],
    AUDIT_ORIGIN_LABELS[event.origin],
    AUDIT_EVIDENCE_LABELS[event.evidence],
    event.requestId,
    event.idempotency.key,
    event.id,
  ]
    .join(" ")
    .toLowerCase()
  return query.text
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((part) => normalizedIncludes(haystack, part))
}

export type AuditListFilter = {
  query: string
  view: AuditSavedViewId
  result: AuditResult | "all"
  origin: AuditOrigin | "all"
  range: AuditRange
}

export const DEFAULT_AUDIT_FILTER: AuditListFilter = {
  query: "",
  view: "all",
  result: "all",
  origin: "all",
  range: "7d",
}

export function filterAuditEvents(
  events: AuditEvent[],
  filter: AuditListFilter,
  now = GOVERN_NOW,
): AuditEvent[] {
  const query = parseAuditQuery(filter.query)
  const cutoff = Date.parse(auditRangeCutoff(filter.range, now))
  return events.filter((event) => {
    if (Date.parse(event.at) < cutoff) return false
    if (!auditMatchesView(event, filter.view)) return false
    if (filter.result !== "all" && event.result !== filter.result) return false
    if (filter.origin !== "all" && event.origin !== filter.origin) return false
    return matchesParsedQuery(event, query)
  })
}

export type AuditResultCounts = {
  applied: number
  rejected: number
  retrying: number
  deadLettered: number
}

export function auditResultCounts(events: AuditEvent[] = auditEvents): AuditResultCounts {
  return {
    applied: events.filter((event) => event.result === "applied").length,
    rejected: events.filter((event) => event.result === "rejected").length,
    retrying: events.filter((event) => event.result === "retrying").length,
    deadLettered: events.filter((event) => event.result === "dead_lettered").length,
  }
}

export type AuditStatus = {
  tone: "muted"
  text: string
  detail: string
}

export function auditStatusLine(events: AuditEvent[] = auditEvents): AuditStatus {
  const counts = auditResultCounts(events)
  return {
    tone: "muted",
    text: "Sample events. The audit stream isn't connected, so integrity can't be checked yet.",
    detail: `${formatGovernNumber(events.length)} events in this range: ${counts.applied} applied, ${counts.rejected} rejected, ${counts.retrying} retrying, ${counts.deadLettered} dead-lettered.`,
  }
}

export type AuditAttentionCounts = {
  retrying: number
  deadLettered: number
  rejected: number
  privileged: number
  /** Null until the integrity endpoint can prove the chain has no gaps. */
  chainGaps: number | null
}

export function auditAttentionCounts(events: AuditEvent[] = auditEvents): AuditAttentionCounts {
  return {
    retrying: events.filter((event) => event.result === "retrying").length,
    deadLettered: events.filter((event) => event.result === "dead_lettered").length,
    rejected: events.filter((event) => event.result === "rejected").length,
    privileged: events.filter((event) => event.stepUp).length,
    chainGaps: null,
  }
}

export function auditDayKey(value: string): string {
  return value.slice(0, 10)
}

export function auditDayLabel(day: string, now = GOVERN_NOW): string {
  const today = new Date(now).toISOString().slice(0, 10)
  const yesterday = new Date(now - 86_400_000).toISOString().slice(0, 10)
  const short = formatGovernShortDate(`${day}T00:00:00Z`)
  if (day === today) return `Today · ${short}`
  if (day === yesterday) return `Yesterday · ${short}`
  return short
}

export type AuditDayGroup = {
  key: string
  label: string
  events: AuditEvent[]
}

export function groupAuditEvents(events: AuditEvent[], now = GOVERN_NOW): AuditDayGroup[] {
  const groups = new Map<string, AuditEvent[]>()
  for (const event of events) {
    const key = auditDayKey(event.at)
    const list = groups.get(key) ?? []
    list.push(event)
    groups.set(key, list)
  }
  return [...groups.entries()].map(([key, list]) => ({ key, label: auditDayLabel(key, now), events: list }))
}

export const AUDIT_PAGE_SIZE = 12

export type AuditPage = {
  items: AuditEvent[]
  loaded: number
  total: number
  hasMore: boolean
  nextCursor: string | null
}

export function auditPage(events: AuditEvent[], cursor: number | null = null): AuditPage {
  const requested = cursor ?? AUDIT_PAGE_SIZE
  const loaded = Math.min(Math.max(requested, AUDIT_PAGE_SIZE), events.length)
  const hasMore = loaded < events.length
  return {
    items: events.slice(0, loaded),
    loaded,
    total: events.length,
    hasMore,
    nextCursor: hasMore ? String(loaded + AUDIT_PAGE_SIZE) : null,
  }
}

export function auditTargetHref(target: AuditTarget): string | null {
  if (target.href !== undefined) return target.href
  switch (target.type) {
    case "directive":
      return `/directives/${target.id}`
    case "policy_snapshot":
      return `/policies/snapshots/${target.id}`
    case "policy_rule":
      return `/policies/rules/${target.id}`
    case "agent":
      return `/agents/${target.id}`
    case "memory":
      return `/memories/${target.id}`
    case "session":
      return `/sessions/${target.id}`
    case "api_key":
      return "/access"
    case "budget":
      return "/budgets"
    case "provider":
      return "/providers"
    case "relay":
      return "/settings"
    case "run":
      return `/explore/r/${target.id}`
    case "tool":
      return "/mcp-tools"
    case "workspace":
      return "/settings"
  }
}

export function auditObjectHref(type: AuditTargetType, id: string): string {
  return `/audit/objects/${type}/${id}`
}

export function auditPolicyHref(policy: AuditPolicyDecision): string {
  return `/policies/rules/${policy.ruleId}?snapshot=${policy.snapshotId}&rev=${policy.ruleRevision}`
}

export function auditEvidenceHref(event: AuditEvent): string {
  return `/evidence?event=${event.id}`
}

export function auditRelated(event: AuditEvent, events: AuditEvent[] = auditEvents): AuditEvent[] {
  const time = Date.parse(event.at)
  return events
    .filter((other) => {
      if (other.id === event.id) return false
      if (event.relatedIds.includes(other.id)) return true
      if (other.requestId === event.requestId) return true
      if (other.idempotency.key === event.idempotency.key) return true
      if (
        other.target.type === event.target.type &&
        other.target.id === event.target.id &&
        Math.abs(Date.parse(other.at) - time) <= 3_600_000
      ) {
        return true
      }
      if (
        event.policy &&
        other.policy &&
        other.action.startsWith("policy.evaluate") &&
        other.policy.ruleId === event.policy.ruleId &&
        other.policy.snapshotId === event.policy.snapshotId
      ) {
        return true
      }
      return false
    })
    .sort((left, right) => Date.parse(right.at) - Date.parse(left.at))
}

export function auditObjectEvents(
  type: AuditTargetType,
  id: string,
  includeFailed = false,
  events: AuditEvent[] = auditEvents,
): AuditEvent[] {
  return events
    .filter((event) => event.target.type === type && event.target.id === id)
    .filter((event) => includeFailed || event.result === "applied")
    .sort((left, right) => Date.parse(right.at) - Date.parse(left.at))
}

export type AuditObjectSummary = {
  events: AuditEvent[]
  count: number
  applied: number
  failed: number
  actors: string[]
  firstAt: string | null
  lastAt: string | null
}

export function auditObjectSummary(
  type: AuditTargetType,
  id: string,
  events: AuditEvent[] = auditEvents,
): AuditObjectSummary {
  const all = auditObjectEvents(type, id, true, events)
  return {
    events: all,
    count: all.length,
    applied: all.filter((event) => event.result === "applied").length,
    failed: all.filter((event) => event.result !== "applied").length,
    actors: [...new Set(all.map((event) => event.actor.name))],
    firstAt: all.at(-1)?.at ?? null,
    lastAt: all[0]?.at ?? null,
  }
}

export type AuditChangedKey = {
  key: string
  before: unknown
  after: unknown
}

export function auditDiffChangedKeys(diff: AuditDiff): AuditChangedKey[] {
  const keys = new Set([...Object.keys(diff.before), ...Object.keys(diff.after)])
  return [...keys]
    .filter((key) => JSON.stringify(diff.before[key]) !== JSON.stringify(diff.after[key]))
    .map((key) => ({ key, before: diff.before[key], after: diff.after[key] }))
}

export function auditDiffChangedCount(diff: AuditDiff): number {
  return auditDiffChangedKeys(diff).length
}

export type AuditIdempotencyAnswer = {
  label: string
  detail: string
  effects: number
  duplicates: number
  ok: boolean
}

export function auditIdempotencyAnswer(event: AuditEvent): AuditIdempotencyAnswer {
  const { effects, duplicates } = event.idempotency
  const effectsLabel = `${effects} effect${effects === 1 ? "" : "s"} applied`
  const duplicatesLabel = `${duplicates} duplicate${duplicates === 1 ? "" : "s"} ignored`
  if (event.result === "rejected") {
    return {
      label: "No effect",
      detail: "The request was rejected before any effect was applied.",
      effects,
      duplicates,
      ok: effects === 0,
    }
  }
  if (event.result === "retrying") {
    return {
      label: "No effect yet",
      detail: "The delivery has not been accepted, so no effect was applied. A retry is scheduled.",
      effects,
      duplicates,
      ok: effects === 0,
    }
  }
  if (event.result === "dead_lettered") {
    return {
      label: "No effect",
      detail: "Retries were exhausted and the delivery was dead-lettered.",
      effects,
      duplicates,
      ok: effects === 0,
    }
  }
  return {
    label: "Applied exactly once",
    detail: `${effectsLabel} · ${duplicatesLabel}`,
    effects,
    duplicates,
    ok: effects === 1,
  }
}

export function auditPrevNext(
  eventId: string,
  events: AuditEvent[] = auditEvents,
): { previous: AuditEvent | null; next: AuditEvent | null; index: number; total: number } {
  const index = events.findIndex((event) => event.id === eventId)
  if (index < 0) return { previous: null, next: null, index: -1, total: events.length }
  return {
    previous: index > 0 ? events[index - 1]! : null,
    next: index < events.length - 1 ? events[index + 1]! : null,
    index,
    total: events.length,
  }
}

export function auditEventJson(event: AuditEvent): Record<string, unknown> {
  return {
    id: event.id,
    occurred_at: event.at,
    actor: { name: event.actor.name, type: event.actor.type, auth: auditActorAuth(event) },
    action: event.action,
    action_category: auditAction(event.action).category,
    target: { type: event.target.type, id: event.target.id, name: event.target.name },
    origin: event.origin,
    result: event.result,
    evidence: event.evidence,
    request_id: event.requestId,
    idempotency_key: event.idempotency.key,
    idempotency: event.idempotency,
    request: event.request,
    policy: event.policy,
    diff: event.diff ?? null,
    retry: event.retry ?? null,
    related_event_ids: auditRelated(event).map((related) => related.id),
  }
}

export const AUDIT_INTEGRITY_CONTRACT = "operator.audit.integrity.v1"
export const AUDIT_INTEGRITY_PENDING = "Integrity checks aren't connected. No verification claim is made."
export const AUDIT_EXPORT_CONTRACT = "operator.audit.export.v1"
export const AUDIT_EXPORT_LOCK_REASON = "Export needs a defined completeness boundary and access-control contract."

/** Null until the integrity contract exists; pages must render PendingData instead of a claim. */
export const auditIntegrity: null = null

export type AuditRetention = {
  label: string
  source: string
}

export const auditRetention: AuditRetention = {
  label: "7 years",
  source: "Workspace data agreement, section 4",
}

export type AuditExportBoundary = {
  count: number
  earliest: string | null
  latest: string | null
  text: string
}

export function auditExportBoundary(events: AuditEvent[] = auditEvents): AuditExportBoundary {
  const sorted = [...events].sort((left, right) => Date.parse(left.at) - Date.parse(right.at))
  const earliest = sorted[0]?.at ?? null
  const latest = sorted.at(-1)?.at ?? null
  return {
    count: sorted.length,
    earliest,
    latest,
    text:
      earliest && latest
        ? `This export will include ${formatGovernNumber(sorted.length)} events from ${formatGovernStamp(earliest)} to ${formatGovernStamp(latest)}.`
        : "No events in this range.",
  }
}

export type AuditExportRecord = {
  id: string
  actor: string
  at: string
  range: string
  hash: string
}

/** Empty until `operator.audit.export.v1` ships; the page shows the empty state. */
export const auditExportHistory: AuditExportRecord[] = []

export const AUDIT_EXPORT_FORMATS = ["Signed NDJSON", "CSV"] as const
