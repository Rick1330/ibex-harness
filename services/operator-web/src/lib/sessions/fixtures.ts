import type {
  CascadePreview,
  GovernedJob,
  MemoryDetail,
  MemoryListItem,
  ReplaySandboxState,
  SessionDetail,
  SessionListItem,
} from "./types"

const AGENTS = [
  "Support Agent",
  "billing-bot",
  "docs-helper",
  "triage",
  "scheduler",
] as const

const STATUSES = [
  "completed",
  "active",
  "failed",
  "suspended",
  "abandoned",
  "initializing",
  "resuming",
] as const

export const SESSION_DETAIL_PRIMARY: SessionDetail = {
  session_id: "sess_client_abc123",
  org: "Acme Corp",
  agent: "Support Agent",
  status: "completed",
  turn_count: 4,
  duration_ms: 2458,
  directive_version: 12,
  last_heartbeat_ago: "2m",
  started_at: "2024-01-20T15:00:05.000Z",
  tags: ["prod", "refund"],
  model: "gpt-4-turbo",
  embedding_profile: "text-embedding-3-large@v2",
  embedding_mismatch: false,
  turns: [
    {
      sequence_number: 1,
      kind: "inference_request",
      at: "2024-01-20T15:00:05.000Z",
      summary: "model: gpt-4-turbo · 2048tk budget",
      request_id: "req_88ac",
      trace_id: "trace_a91f7c",
      model: "gpt-4-turbo",
      tokens: 2048,
      evidence_state: "present",
      directive_version: 12,
      directive_hash: "9f2a",
      conversation_preview: "Customer asks about enterprise refund window…",
      context_assembly: {
        directive: 420,
        history: 800,
        memories: 640,
        tools: 140,
        budget: 2000,
      },
    },
    {
      sequence_number: 2,
      kind: "memory_read",
      at: "2024-01-20T15:00:05.042Z",
      summary: '3 memories · q:"prefs"',
      request_id: "req_88ac",
      trace_id: "trace_a91f7c",
      evidence_state: "present",
      memories: [
        {
          memory_id: "mem_a1b2c3d4",
          category: "factual",
          retrieval_similarity: 0.91,
          composite_score: 0.87,
          final_rank: 1,
          components: {
            relevance: 0.95,
            recency: 0.98,
            usefulness: 0.8,
            confidence: 0.9,
            frequency: 0.6,
          },
        },
        {
          memory_id: "mem_7c11e2",
          category: "preference",
          retrieval_similarity: 0.88,
          composite_score: 0.71,
          final_rank: 3,
          components: {
            relevance: 0.88,
            recency: 0.72,
            usefulness: 0.55,
            confidence: 0.7,
            frequency: 0.4,
          },
        },
        {
          memory_id: "mem_4e88aa",
          category: "procedural",
          retrieval_similarity: 0.84,
          composite_score: 0.78,
          final_rank: 2,
          components: {
            relevance: 0.84,
            recency: 0.9,
            usefulness: 0.7,
            confidence: 0.75,
            frequency: 0.5,
          },
        },
      ],
    },
    {
      sequence_number: 3,
      kind: "tool_call",
      at: "2024-01-20T15:00:06.100Z",
      summary: "search() · idempotent",
      tool_name: "search",
      idempotent: true,
      latency_ms: 310,
      evidence_state: "present",
      request_id: "req_88ac",
      trace_id: "trace_a91f7c",
    },
    {
      sequence_number: 4,
      kind: "inference_response",
      at: "2024-01-20T15:00:07.500Z",
      summary: "342tk · 2458ms",
      tokens: 342,
      latency_ms: 2458,
      evidence_state: "present",
      request_id: "req_88ac",
      trace_id: "trace_a91f7c",
      conversation_preview:
        "Enterprise refunds are eligible within 30 days of invoice…",
    },
    {
      sequence_number: 5,
      kind: "checkpoint",
      at: "2024-01-20T15:00:07.520Z",
      summary: "checkpoint ckpt_01h9 — resume bridge",
      checkpoint_id: "ckpt_01h9",
      evidence_state: "present",
    },
    {
      sequence_number: 6,
      kind: "sampled",
      at: "2024-01-20T15:00:07.600Z",
      summary: "sampled span omitted from hot path",
      evidence_state: "sampled",
    },
  ],
}

export const SESSION_LIST: SessionListItem[] = [
  listFrom(SESSION_DETAIL_PRIMARY),
  ...Array.from({ length: 47 }, (_, i) => {
    const n = i + 1
    const status = STATUSES[n % STATUSES.length]
    return {
      session_id: `sess_${(0xabc100 + n).toString(16)}`,
      agent: AGENTS[n % AGENTS.length],
      status,
      turn_count: 2 + (n % 14),
      duration_ms: 800 + n * 97,
      directive_version: 10 + (n % 3),
      last_heartbeat_ago: `${(n % 40) + 1}m`,
      started_at: new Date(
        Date.parse("2024-01-20T15:00:05.000Z") - n * 11 * 60_000,
      ).toISOString(),
      tags:
        n % 3 === 0 ? ["prod"] : n % 2 === 0 ? ["staging"] : ["prod", "sla"],
      model: n % 2 === 0 ? "gpt-4-turbo" : "claude-3-opus",
    } satisfies SessionListItem
  }),
]

export const SESSION_BY_ID: Record<string, SessionDetail> = {
  [SESSION_DETAIL_PRIMARY.session_id]: SESSION_DETAIL_PRIMARY,
  // Lightweight detail stubs for list deep-links
  ...Object.fromEntries(
    SESSION_LIST.slice(1, 8).map((s) => [
      s.session_id,
      {
        ...s,
        org: "Acme Corp",
        turns: [
          {
            sequence_number: 1,
            kind: "inference_request" as const,
            at: s.started_at,
            summary: `model: ${s.model}`,
            model: s.model,
            evidence_state: "present" as const,
            request_id: `req_${s.session_id.slice(-4)}`,
            trace_id: "trace_a91f7c",
            directive_version: s.directive_version,
            directive_hash: "9f2a",
          },
          {
            sequence_number: 2,
            kind: "inference_response" as const,
            at: s.started_at,
            summary: `${120 + s.turn_count}tk · ${s.duration_ms}ms`,
            tokens: 120 + s.turn_count,
            latency_ms: s.duration_ms,
            evidence_state: "present" as const,
          },
        ],
      } satisfies SessionDetail,
    ]),
  ),
}

export const MEMORY_DETAIL_PRIMARY: MemoryDetail = {
  memory_id: "mem_a1b2c3d4",
  category: "factual",
  preview: "Enterprise refund window is 30 days from invoice date…",
  content:
    "Enterprise refund window is 30 days from invoice date for annual contracts. Escalation to P2 when refund amount exceeds $500.",
  confidence: 0.95,
  usefulness: 0.82,
  lifecycle: "active",
  visibility: "org",
  retrieved_in_sessions: 12,
  avg_composite: 0.82,
  updated_at: "2024-01-18T11:22:00.000Z",
  lineage_truncated: true,
  embedding_model: "text-embedding-3-large",
  embedding_version: "v2",
  current_embedding_version: "v2",
  embedding_mismatch: false,
  retrieval_note:
    "similarity is the retrieval-stage cosine; final_rank is post-composite order — never treat them as the same.",
  lineage: [
    {
      kind: "supersedes",
      direction: "from",
      memory_id: "mem_9f2a11",
      status: "archived",
      at: "2024-01-02",
    },
    {
      kind: "contradicts",
      direction: "to",
      memory_id: "mem_7c11e2",
      status: "quarantined",
      note: "flagged, needs review",
    },
    {
      kind: "specializes",
      direction: "from",
      memory_id: "mem_4e88aa",
      status: "active",
    },
  ],
}

export const MEMORY_LIST: MemoryListItem[] = [
  listMem(MEMORY_DETAIL_PRIMARY),
  {
    memory_id: "mem_7c11e2",
    category: "preference",
    preview: "Customer prefers email follow-ups over chat…",
    confidence: 0.7,
    usefulness: 0.55,
    lifecycle: "quarantined",
    visibility: "agent",
    retrieved_in_sessions: 4,
    avg_composite: 0.61,
    updated_at: "2024-01-15T09:00:00.000Z",
  },
  {
    memory_id: "mem_4e88aa",
    category: "procedural",
    preview: "Always verify SLA credit eligibility before quoting…",
    confidence: 0.88,
    usefulness: 0.79,
    lifecycle: "active",
    visibility: "org",
    retrieved_in_sessions: 9,
    avg_composite: 0.76,
    updated_at: "2024-01-17T14:10:00.000Z",
  },
  {
    memory_id: "mem_9f2a11",
    category: "factual",
    preview: "Legacy refund window was 14 days (superseded)…",
    confidence: 0.6,
    usefulness: 0.2,
    lifecycle: "archived",
    visibility: "org",
    retrieved_in_sessions: 1,
    avg_composite: 0.3,
    updated_at: "2024-01-02T08:00:00.000Z",
  },
  ...Array.from({ length: 36 }, (_, i) => {
    const n = i + 1
    const cats = [
      "factual",
      "preference",
      "behavioral",
      "episodic",
      "procedural",
    ] as const
    const life = [
      "active",
      "active",
      "superseded",
      "archived",
      "quarantined",
    ] as const
    return {
      memory_id: `mem_${(0x1000 + n).toString(16)}`,
      category: cats[n % cats.length],
      preview: `Memory fixture #${n} — operator-facing preview text.`,
      confidence: 0.4 + (n % 50) / 100,
      usefulness: 0.3 + (n % 60) / 100,
      lifecycle: life[n % life.length],
      visibility: n % 2 === 0 ? "org" : "agent",
      retrieved_in_sessions: n % 15,
      avg_composite: 0.45 + (n % 40) / 100,
      updated_at: new Date(
        Date.parse("2024-01-18T11:22:00.000Z") - n * 36 * 60_000,
      ).toISOString(),
    } satisfies MemoryListItem
  }),
]

export const MEMORY_BY_ID: Record<string, MemoryDetail> = {
  [MEMORY_DETAIL_PRIMARY.memory_id]: MEMORY_DETAIL_PRIMARY,
  mem_7c11e2: {
    ...MEMORY_LIST[1],
    content: "Customer prefers email follow-ups over chat for refund outcomes.",
    lineage: [
      {
        kind: "contradicts",
        direction: "from",
        memory_id: "mem_a1b2c3d4",
        status: "active",
        note: "unresolved pending_review",
      },
    ],
    lineage_truncated: false,
    embedding_model: "text-embedding-3-large",
    embedding_version: "v1",
    current_embedding_version: "v2",
    embedding_mismatch: true,
    retrieval_note:
      "Embedding version mismatch — scores may not be comparable to current config.",
  },
  mem_4e88aa: {
    ...MEMORY_LIST[2],
    content:
      "Always verify SLA credit eligibility before quoting refund amounts.",
    lineage: [
      {
        kind: "specializes",
        direction: "to",
        memory_id: "mem_a1b2c3d4",
        status: "active",
      },
    ],
    lineage_truncated: false,
    embedding_model: "text-embedding-3-large",
    embedding_version: "v2",
    current_embedding_version: "v2",
    embedding_mismatch: false,
    retrieval_note:
      "similarity ≠ rank — composite reordering applied after retrieval.",
  },
  mem_9f2a11: {
    ...MEMORY_LIST[3],
    content: "Legacy refund window was 14 days (superseded by mem_a1b2c3d4).",
    lineage: [
      {
        kind: "supersedes",
        direction: "to",
        memory_id: "mem_a1b2c3d4",
        status: "active",
        at: "2024-01-02",
      },
    ],
    lineage_truncated: false,
    embedding_model: "text-embedding-3-large",
    embedding_version: "v2",
    current_embedding_version: "v2",
    embedding_mismatch: false,
    retrieval_note: "Archived successor — do not pack above active successors.",
  },
}

export const DELETE_PREVIEW: CascadePreview = {
  target_label: "session",
  target_id: "sess_client_abc123",
  kind: "delete",
  legal_hold: "none",
  legal_hold_note: "none active — proceeding allowed",
  stores: [
    {
      store: "Postgres",
      detail: "session_events, checkpoints",
      rows_or_objects: 1204,
      unit: "rows",
      ok: true,
    },
    {
      store: "ClickHouse",
      detail: "llm_traces projection",
      rows_or_objects: 340,
      unit: "rows",
      ok: true,
    },
    {
      store: "Object storage",
      detail: "archived_to payloads",
      rows_or_objects: 3,
      unit: "objects",
      ok: true,
    },
  ],
}

export const JOB_LIST: GovernedJob[] = [
  {
    job_id: "job_exp_01",
    kind: "export",
    target_id: "sess_client_abc123",
    status: "completed",
    created_at: "2024-01-20T16:00:00.000Z",
    receipts: [
      {
        store: "Postgres",
        status: "verified",
        detail: "1,204 rows exported",
      },
      {
        store: "ClickHouse",
        status: "verified",
        detail: "340 rows exported",
      },
      {
        store: "Object storage",
        status: "verified",
        detail: "3 objects bundled",
      },
    ],
  },
  {
    job_id: "job_del_02",
    kind: "delete",
    target_id: "sess_a1c0",
    status: "completed",
    created_at: "2024-01-20T16:10:00.000Z",
    receipts: [
      {
        store: "Postgres",
        status: "verified",
        detail: "880 rows removed",
      },
      {
        store: "ClickHouse",
        status: "verified",
        detail: "210 rows removed",
      },
      {
        store: "Object storage",
        status: "not_applicable",
        detail: "no archived payloads",
      },
    ],
  },
  {
    job_id: "job_rep_03",
    kind: "replay",
    target_id: "sess_client_abc123",
    status: "completed",
    created_at: "2024-01-20T16:12:00.000Z",
    receipts: [
      {
        store: "Sandbox",
        status: "verified",
        detail: "replay_req_9f11 audited separately",
      },
    ],
  },
]

export const REPLAY_FIXTURE: ReplaySandboxState = {
  snapshot_at: "2024-01-20T15:00:05.000Z",
  directive_version: 12,
  directive_hash: "9f2a",
  model_version: "gpt-4-turbo-2024-04",
  tokenizer_version: "v3",
  packing_policy_version: "v2",
  original: {
    tool: "search()",
    tool_result: "3 results",
    tokens: 342,
    latency_ms: 2458,
  },
  replayed: {
    tool: "search()",
    mocked: true,
    tool_result: "original cached args used",
    tokens: 340,
    latency_ms: 2401,
  },
  diff: {
    tokens_delta: -2,
    latency_delta_ms: -57,
    semantic_diff: false,
    summary: "no semantic diff detected",
  },
  audit_request_id: "replay_req_9f11",
  original_request_id: "req_88ac",
}

function listFrom(s: SessionDetail): SessionListItem {
  return {
    session_id: s.session_id,
    agent: s.agent,
    status: s.status,
    turn_count: s.turn_count,
    duration_ms: s.duration_ms,
    directive_version: s.directive_version,
    last_heartbeat_ago: s.last_heartbeat_ago,
    started_at: s.started_at,
    tags: s.tags,
    model: s.model,
  }
}

function listMem(m: MemoryDetail): MemoryListItem {
  return {
    memory_id: m.memory_id,
    category: m.category,
    preview: m.preview,
    confidence: m.confidence,
    usefulness: m.usefulness,
    lifecycle: m.lifecycle,
    visibility: m.visibility,
    retrieved_in_sessions: m.retrieved_in_sessions,
    avg_composite: m.avg_composite,
    updated_at: m.updated_at,
  }
}
