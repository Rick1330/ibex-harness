import type { EvidenceBundle, IncidentDetail, IncidentListItem } from "./types"

const BUNDLE_SAMPLE: EvidenceBundle = {
  bundle_id: "bundle_ev_91a",
  signed: true,
  hash: "sha256:7c1e9f2a…d4b1",
  exported_at: "2024-01-20T16:40:00.000Z",
  exported_by: "sara",
  contents: [
    "incident timeline",
    "linked trace/session snapshots",
    "redacted payloads",
    "directive v12 @ 9f2a",
    "action ledger",
  ],
  no_secrets: true,
  no_cross_tenant: true,
  audit_event_id: "audit_bundle_91a",
}

export const INCIDENT_PRIMARY: IncidentDetail = {
  incident_id: "inc_7f2a",
  org: "Acme Corp",
  severity: "sev1",
  status: "mitigating",
  title: "Checkout provider timeout spike",
  dedupe_key: "provider_timeout_x",
  owner: "sara",
  linked_trace_count: 14,
  linked_session_count: 3,
  age: "2h",
  last_activity: "12m ago",
  created_at: "2024-01-20T15:02:00.000Z",
  description:
    "Elevated OpenAI timeout rate on checkout sessions after directive v12 promotion. Auto-opened from drift alert.",
  directive_snapshot: {
    version: 12,
    hash: "9f2a",
    at: "2024-01-20T14:50:00.000Z",
  },
  payload_sanitized: `{
  "error": "provider_timeout",
  "provider": "openai",
  "model": "gpt-4-turbo",
  "sample_rate": 0.42,
  "message": "[sanitized] timeout waiting for completion"
}`,
  payload_raw_available: true,
  linked: [
    {
      kind: "trace",
      id: "trace_a91f7c",
      label: "trace_a91f · provider timeout",
      href: "/dashboard/explore/t/trace_a91f7c",
    },
    {
      kind: "trace",
      id: "trace_b02e44",
      label: "trace_b02e · partial / budget",
      href: "/dashboard/explore/t/trace_b02e44",
    },
    {
      kind: "session",
      id: "sess_client_abc123",
      label: "sess_client_abc123 · 4 turns",
      href: "/dashboard/sessions/sess_client_abc123",
    },
    {
      kind: "request",
      id: "req_88ac",
      label: "req_88ac",
      href: "/dashboard/explore?q=request:req_88ac",
    },
  ],
  timeline: [
    {
      id: "tl_1",
      kind: "state_transition",
      at: "2024-01-20T15:02:00.000Z",
      actor: "system",
      summary: "opened (auto, from drift alert)",
      after: "open",
      transition_key: "inc_7f2a:open",
    },
    {
      id: "tl_2",
      kind: "state_transition",
      at: "2024-01-20T15:04:00.000Z",
      actor: "sara",
      summary: "acknowledged",
      before: "open",
      after: "acknowledged",
      transition_key: "inc_7f2a:acknowledged",
    },
    {
      id: "tl_3",
      kind: "ownership",
      at: "2024-01-20T15:04:05.000Z",
      actor: "sara",
      summary: "claimed ownership",
      before: "unassigned",
      after: "sara",
    },
    {
      id: "tl_4",
      kind: "state_transition",
      at: "2024-01-20T15:10:00.000Z",
      actor: "sara",
      summary: '→ mitigating · comment: "rolling back directive v12"',
      before: "acknowledged",
      after: "mitigating",
      transition_key: "inc_7f2a:mitigating",
    },
    {
      id: "tl_5",
      kind: "comment",
      at: "2024-01-20T15:10:00.000Z",
      actor: "sara",
      summary: "rolling back directive v12",
    },
    {
      id: "tl_6",
      kind: "link",
      at: "2024-01-20T15:22:00.000Z",
      actor: "sara",
      summary: "linked trace_a91f, trace_b02e (provider timeout pattern)",
    },
  ],
  bundles: [],
}

export const INCIDENT_SEV2: IncidentDetail = {
  incident_id: "inc_3b91",
  org: "Acme Corp",
  severity: "sev2",
  status: "open",
  title: "Directive v12 elevated error rate",
  dedupe_key: "directive_v12_error_rate",
  owner: null,
  linked_trace_count: 8,
  linked_session_count: 2,
  age: "5h",
  last_activity: "1h ago",
  created_at: "2024-01-20T12:00:00.000Z",
  description:
    "Error rate crossed band after directive promote. Awaiting owner assignment.",
  directive_snapshot: {
    version: 12,
    hash: "9f2a",
    at: "2024-01-20T11:40:00.000Z",
  },
  payload_sanitized: `{
  "error": "elevated_error_rate",
  "directive_version": 12,
  "rate": 0.08,
  "baseline": 0.02
}`,
  payload_raw_available: true,
  linked: [
    {
      kind: "trace",
      id: "trace_a91f7c",
      label: "trace_a91f",
      href: "/dashboard/explore/t/trace_a91f7c",
    },
  ],
  timeline: [
    {
      id: "tl_s2_1",
      kind: "state_transition",
      at: "2024-01-20T12:00:00.000Z",
      actor: "system",
      summary: "opened (auto, error-rate band)",
      after: "open",
      transition_key: "inc_3b91:open",
    },
  ],
  bundles: [],
}

export const INCIDENT_SEV3: IncidentDetail = {
  incident_id: "inc_1c04",
  org: "Acme Corp",
  severity: "sev3",
  status: "acknowledged",
  title: "Memory extraction backlog",
  dedupe_key: "memory_extract_backlog",
  owner: "devon",
  linked_trace_count: 3,
  linked_session_count: 1,
  age: "1d",
  last_activity: "4h ago",
  created_at: "2024-01-19T15:00:00.000Z",
  description: "Episodic extraction lag above SLO. Non-customer-facing.",
  directive_snapshot: {
    version: 11,
    hash: "4e88",
    at: "2024-01-18T10:00:00.000Z",
  },
  payload_sanitized: `{
  "queue_depth": 4200,
  "lag_p95_ms": 180000
}`,
  payload_raw_available: false,
  linked: [
    {
      kind: "session",
      id: "sess_client_abc123",
      label: "sess_client_abc123",
      href: "/dashboard/sessions/sess_client_abc123",
    },
  ],
  timeline: [
    {
      id: "tl_s3_1",
      kind: "state_transition",
      at: "2024-01-19T15:00:00.000Z",
      actor: "system",
      summary: "opened",
      after: "open",
      transition_key: "inc_1c04:open",
    },
    {
      id: "tl_s3_2",
      kind: "state_transition",
      at: "2024-01-19T16:00:00.000Z",
      actor: "devon",
      summary: "acknowledged",
      before: "open",
      after: "acknowledged",
      transition_key: "inc_1c04:acknowledged",
    },
    {
      id: "tl_s3_3",
      kind: "ownership",
      at: "2024-01-19T16:00:05.000Z",
      actor: "devon",
      summary: "assigned",
      before: "unassigned",
      after: "devon",
    },
  ],
  bundles: [BUNDLE_SAMPLE],
}

export const INCIDENT_BY_ID: Record<string, IncidentDetail> = {
  [INCIDENT_PRIMARY.incident_id]: INCIDENT_PRIMARY,
  [INCIDENT_SEV2.incident_id]: INCIDENT_SEV2,
  [INCIDENT_SEV3.incident_id]: INCIDENT_SEV3,
}

function listFrom(i: IncidentDetail): IncidentListItem {
  return {
    incident_id: i.incident_id,
    severity: i.severity,
    status: i.status,
    title: i.title,
    dedupe_key: i.dedupe_key,
    owner: i.owner,
    linked_trace_count: i.linked_trace_count,
    linked_session_count: i.linked_session_count,
    age: i.age,
    last_activity: i.last_activity,
    created_at: i.created_at,
  }
}

export const INCIDENT_LIST: IncidentListItem[] = [
  listFrom(INCIDENT_PRIMARY),
  listFrom(INCIDENT_SEV2),
  listFrom(INCIDENT_SEV3),
  ...Array.from({ length: 24 }, (_, n) => {
    const sev = (["sev2", "sev3", "sev4"] as const)[n % 3]
    const status = (
      ["open", "acknowledged", "mitigating", "resolved", "closed"] as const
    )[n % 5]
    return {
      incident_id: `inc_gen_${String(n + 10).padStart(2, "0")}`,
      severity: sev,
      status,
      title:
        n % 2 === 0
          ? `Synthetic failure signature ${n + 10}`
          : `Provider flake cluster ${n + 10}`,
      dedupe_key: `sig_${n % 7}`,
      owner: n % 3 === 0 ? null : n % 2 === 0 ? "sara" : "devon",
      linked_trace_count: (n % 9) + 1,
      linked_session_count: n % 4,
      age: `${(n % 12) + 1}h`,
      last_activity: `${(n % 50) + 1}m ago`,
      created_at: `2024-01-${String(18 + (n % 3)).padStart(2, "0")}T${String(10 + (n % 8)).padStart(2, "0")}:00:00.000Z`,
    } satisfies IncidentListItem
  }),
]

export { BUNDLE_SAMPLE }
