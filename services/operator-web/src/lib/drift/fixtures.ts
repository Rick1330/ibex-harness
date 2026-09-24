import type {
  AgentDriftPolicy,
  ClusterMass,
  DriftAlertDetail,
  DriftAlertListItem,
  FeatureEvidence,
  FingerprintRow,
  QuantileSketch,
} from "./types"

function sketch(
  p10: number,
  p25: number,
  p50: number,
  p75: number,
  p90: number,
): QuantileSketch {
  return { p10, p25, p50, p75, p90 }
}

const clusters = (a: number, b: number, c: number): ClusterMass[] => [
  { cluster: "resolve", mass: a },
  { cluster: "clarify", mass: b },
  { cluster: "escalate", mass: c },
]

const evidenceSupport: FeatureEvidence[] = [
  {
    feature_class: "token_quantile_sketch",
    test: "ks_two_sample",
    test_statistic: 0.41,
    threshold_used: 0.22,
    p_value: 0.003,
    n_baseline: 1840,
    n_current: 620,
    baseline_summary: "prompt tokens median 820 · p90 1.4k",
    current_summary: "prompt tokens median 1.6k · p90 3.1k",
    flagged: true,
    baseline_sketch: sketch(420, 610, 820, 1180, 1400),
    current_sketch: sketch(680, 1100, 1600, 2600, 3100),
    baseline_tools: null,
    current_tools: null,
    baseline_clusters: null,
    current_clusters: null,
    baseline_successes: null,
    baseline_trials: null,
    current_successes: null,
    current_trials: null,
  },
  {
    feature_class: "tool_distribution_smoothed",
    test: "jensen_shannon",
    test_statistic: 0.28,
    threshold_used: 0.15,
    p_value: null,
    n_baseline: 1840,
    n_current: 620,
    baseline_summary: "kb.search 0.42 · ticket.lookup 0.31 · crm.get 0.27",
    current_summary: "kb.search 0.11 · ticket.lookup 0.18 · crm.get 0.71",
    flagged: true,
    baseline_sketch: null,
    current_sketch: null,
    baseline_tools: [
      { tool: "kb.search", mass: 0.42 },
      { tool: "ticket.lookup", mass: 0.31 },
      { tool: "crm.get", mass: 0.27 },
    ],
    current_tools: [
      { tool: "kb.search", mass: 0.11 },
      { tool: "ticket.lookup", mass: 0.18 },
      { tool: "crm.get", mass: 0.71 },
    ],
    baseline_clusters: null,
    current_clusters: null,
    baseline_successes: null,
    baseline_trials: null,
    current_successes: null,
    current_trials: null,
  },
  {
    feature_class: "response_cluster_centroids",
    test: "chi_squared_cluster",
    test_statistic: 18.4,
    threshold_used: 12.6,
    p_value: 0.0001,
    n_baseline: 1840,
    n_current: 620,
    baseline_summary: "3 centroids · membership χ² stable",
    current_summary: "membership shift toward escalate cluster",
    flagged: true,
    baseline_sketch: null,
    current_sketch: null,
    baseline_tools: null,
    current_tools: null,
    baseline_clusters: clusters(0.52, 0.33, 0.15),
    current_clusters: clusters(0.28, 0.22, 0.5),
    baseline_successes: null,
    baseline_trials: null,
    current_successes: null,
    current_trials: null,
  },
  {
    feature_class: "error_successes",
    test: "beta_binomial_ci",
    test_statistic: 0.96,
    threshold_used: 0.95,
    p_value: null,
    n_baseline: 1840,
    n_current: 620,
    baseline_summary: "error rate 1.1% · CI overlaps baseline",
    current_summary: "error rate 3.4% · credible intervals diverge",
    flagged: true,
    baseline_sketch: null,
    current_sketch: null,
    baseline_tools: null,
    current_tools: null,
    baseline_clusters: null,
    current_clusters: null,
    baseline_successes: 1820,
    baseline_trials: 1840,
    current_successes: 599,
    current_trials: 620,
  },
]

export const DRIFT_ALERT_PRIMARY: DriftAlertDetail = {
  alert_id: "drift_7f2a91",
  org_id: "org_acme",
  agent_id: "agt_01h9support",
  agent_name: "Support Agent",
  agent_slug: "support-agent",
  severity: "high",
  status: "open",
  feature_classes: [
    "token_quantile_sketch",
    "tool_distribution_smoothed",
    "response_cluster_centroids",
    "error_successes",
  ],
  action_taken: "logged",
  drift_action_stage: "shadow",
  created_at: "2026-02-11T14:05:00.000Z",
  acknowledged_at: null,
  acknowledged_by: null,
  resolved_at: null,
  resolution_notes: null,
  evidence: evidenceSupport,
  contributing_trace_ids: ["trace_a91f7c", "trace_b02e44"],
  window_start: "2026-02-11T12:00:00.000Z",
  window_end: "2026-02-11T14:00:00.000Z",
  shadow_mode: true,
  shadow_days_remaining: 18,
  triggered_rollout_rollback: true,
  rollback_directive_version: 12,
}

export const DRIFT_ALERT_MEDIUM: DriftAlertDetail = {
  alert_id: "drift_3b91c0",
  org_id: "org_acme",
  agent_id: "agt_01h9billing",
  agent_name: "billing-bot",
  agent_slug: "billing-bot",
  severity: "medium",
  status: "acknowledged",
  feature_classes: ["tool_distribution_smoothed"],
  action_taken: "notified",
  drift_action_stage: "notify",
  created_at: "2026-02-10T09:00:00.000Z",
  acknowledged_at: "2026-02-10T09:40:00.000Z",
  acknowledged_by: "devon@acme.com",
  resolved_at: null,
  resolution_notes: null,
  evidence: [
    {
      feature_class: "tool_distribution_smoothed",
      test: "jensen_shannon",
      test_statistic: 0.19,
      threshold_used: 0.15,
      p_value: null,
      n_baseline: 900,
      n_current: 310,
      baseline_summary: "quote.build dominant 0.55",
      current_summary: "crm.get dominant 0.48",
      flagged: true,
      baseline_sketch: null,
      current_sketch: null,
      baseline_tools: [
        { tool: "quote.build", mass: 0.55 },
        { tool: "crm.get", mass: 0.28 },
        { tool: "invoice.send", mass: 0.17 },
      ],
      current_tools: [
        { tool: "quote.build", mass: 0.22 },
        { tool: "crm.get", mass: 0.48 },
        { tool: "invoice.send", mass: 0.3 },
      ],
      baseline_clusters: null,
      current_clusters: null,
      baseline_successes: null,
      baseline_trials: null,
      current_successes: null,
      current_trials: null,
    },
  ],
  contributing_trace_ids: ["trace_a91f7c"],
  window_start: "2026-02-10T06:00:00.000Z",
  window_end: "2026-02-10T09:00:00.000Z",
  shadow_mode: false,
  shadow_days_remaining: null,
  triggered_rollout_rollback: false,
  rollback_directive_version: null,
}

export const DRIFT_ALERT_LOW: DriftAlertDetail = {
  alert_id: "drift_1c04ee",
  org_id: "org_acme",
  agent_id: "agt_01h9docs",
  agent_name: "docs-helper",
  agent_slug: "docs-helper",
  severity: "low",
  status: "resolved",
  feature_classes: ["token_quantile_sketch"],
  action_taken: "logged",
  drift_action_stage: "shadow",
  created_at: "2026-02-08T11:00:00.000Z",
  acknowledged_at: "2026-02-08T12:00:00.000Z",
  acknowledged_by: "sara@acme.com",
  resolved_at: "2026-02-08T16:00:00.000Z",
  resolution_notes: "Corpus update increased prompt length — expected.",
  evidence: [
    {
      feature_class: "token_quantile_sketch",
      test: "ks_two_sample",
      test_statistic: 0.18,
      threshold_used: 0.22,
      p_value: 0.12,
      n_baseline: 1100,
      n_current: 400,
      baseline_summary: "median 640",
      current_summary: "median 720",
      flagged: false,
      baseline_sketch: sketch(300, 450, 640, 900, 1100),
      current_sketch: sketch(320, 480, 720, 980, 1200),
      baseline_tools: null,
      current_tools: null,
      baseline_clusters: null,
      current_clusters: null,
      baseline_successes: null,
      baseline_trials: null,
      current_successes: null,
      current_trials: null,
    },
  ],
  contributing_trace_ids: [],
  window_start: "2026-02-08T08:00:00.000Z",
  window_end: "2026-02-08T11:00:00.000Z",
  shadow_mode: true,
  shadow_days_remaining: 22,
  triggered_rollout_rollback: false,
  rollback_directive_version: null,
}

export const DRIFT_BY_ID: Record<string, DriftAlertDetail> = {
  [DRIFT_ALERT_PRIMARY.alert_id]: DRIFT_ALERT_PRIMARY,
  [DRIFT_ALERT_MEDIUM.alert_id]: DRIFT_ALERT_MEDIUM,
  [DRIFT_ALERT_LOW.alert_id]: DRIFT_ALERT_LOW,
}

function listFrom(a: DriftAlertDetail): DriftAlertListItem {
  return {
    alert_id: a.alert_id,
    agent_id: a.agent_id,
    agent_name: a.agent_name,
    agent_slug: a.agent_slug,
    severity: a.severity,
    status: a.status,
    feature_classes: a.feature_classes,
    action_taken: a.action_taken,
    drift_action_stage: a.drift_action_stage,
    created_at: a.created_at,
    triggered_rollout_rollback: a.triggered_rollout_rollback,
    rollback_directive_version: a.rollback_directive_version,
  }
}

export const DRIFT_ALERT_LIST: DriftAlertListItem[] = [
  listFrom(DRIFT_ALERT_PRIMARY),
  listFrom(DRIFT_ALERT_MEDIUM),
  listFrom(DRIFT_ALERT_LOW),
  ...Array.from({ length: 12 }, (_, n) => {
    const sev = (["low", "medium", "high"] as const)[n % 3]
    const status = (
      ["open", "acknowledged", "resolved", "false_positive"] as const
    )[n % 4]
    return {
      alert_id: `drift_gen_${String(n + 10).padStart(2, "0")}`,
      agent_id: `agt_gen_${String(n + 10).padStart(2, "0")}`,
      agent_name: `helper-${n + 10}`,
      agent_slug: `helper-${n + 10}`,
      severity: sev,
      status,
      feature_classes: (
        [
          ["token_quantile_sketch"],
          ["tool_distribution_smoothed", "error_trials"],
          ["response_cluster_centroids"],
        ] as const
      )[n % 3].slice() as DriftAlertListItem["feature_classes"],
      action_taken: (["logged", "notified", "suspended"] as const)[n % 3],
      drift_action_stage: (["shadow", "notify", "auto_suspend"] as const)[
        n % 3
      ],
      created_at: `2026-02-${String((n % 10) + 1).padStart(2, "0")}T10:00:00.000Z`,
      triggered_rollout_rollback: false,
      rollback_directive_version: null,
    } satisfies DriftAlertListItem
  }),
]

/** Sorted open + high first — matches idx_drift_alerts_open use case. */
export function sortAlertsDefault(rows: DriftAlertListItem[]) {
  const sevRank = { high: 0, medium: 1, low: 2 }
  const statusRank = {
    open: 0,
    acknowledged: 1,
    resolved: 2,
    false_positive: 3,
  }
  return [...rows].sort((a, b) => {
    const s = statusRank[a.status] - statusRank[b.status]
    if (s !== 0) return s
    return sevRank[a.severity] - sevRank[b.severity]
  })
}

export function getDriftAlert(alertId: string): DriftAlertDetail | null {
  const known = DRIFT_BY_ID[alertId]
  if (known) return known
  const list = DRIFT_ALERT_LIST.find((a) => a.alert_id === alertId)
  if (!list) return null
  return {
    ...list,
    org_id: "org_acme",
    acknowledged_at:
      list.status === "acknowledged" ||
      list.status === "resolved" ||
      list.status === "false_positive"
        ? list.created_at
        : null,
    acknowledged_by:
      list.status === "acknowledged" ||
      list.status === "resolved" ||
      list.status === "false_positive"
        ? "operator@acme.com"
        : null,
    resolved_at:
      list.status === "resolved" || list.status === "false_positive"
        ? list.created_at
        : null,
    resolution_notes:
      list.status === "resolved"
        ? "Fixture resolution."
        : list.status === "false_positive"
          ? "Calibration FP mark."
          : null,
    evidence: [
      {
        feature_class: list.feature_classes[0] ?? "token_quantile_sketch",
        test:
          list.feature_classes[0] === "tool_distribution_smoothed"
            ? "jensen_shannon"
            : list.feature_classes[0] === "response_cluster_centroids"
              ? "chi_squared_cluster"
              : "ks_two_sample",
        test_statistic: 0.31,
        threshold_used: 0.2,
        p_value: 0.04,
        n_baseline: 500,
        n_current: 200,
        baseline_summary: "baseline window",
        current_summary: "current window",
        flagged: true,
        baseline_sketch: sketch(1, 2, 4, 6, 7),
        current_sketch: sketch(2, 3, 7, 11, 13),
        baseline_tools: null,
        current_tools: null,
        baseline_clusters: null,
        current_clusters: null,
        baseline_successes: null,
        baseline_trials: null,
        current_successes: null,
        current_trials: null,
      },
    ],
    contributing_trace_ids: ["trace_a91f7c"],
    window_start: list.created_at,
    window_end: list.created_at,
    shadow_mode: list.drift_action_stage === "shadow",
    shadow_days_remaining: list.drift_action_stage === "shadow" ? 18 : null,
  }
}

export const FINGERPRINTS_SUPPORT: FingerprintRow[] = [
  {
    fingerprint_id: "fp_base",
    computed_at: "2026-01-15T00:00:00.000Z",
    is_baseline: true,
    avg_prompt_tokens: 820,
    tool_call_rate: 2.4,
    error_rate: 0.011,
    avg_response_time_ms: 2100,
    directive_version: 11,
    token_sketch: sketch(420, 610, 820, 1180, 1400),
    cluster_masses: clusters(0.52, 0.33, 0.15),
    adwin_change_point: false,
  },
  ...Array.from({ length: 11 }, (_, n) => {
    const day = n + 1
    const drift = day >= 9
    const med = 820 + n * 55 + (drift ? 200 : 0)
    return {
      fingerprint_id: `fp_w${n}`,
      computed_at: `2026-02-${String(day).padStart(2, "0")}T00:00:00.000Z`,
      is_baseline: false,
      avg_prompt_tokens: med,
      tool_call_rate: 2.4 + n * 0.08,
      error_rate: 0.011 + n * 0.002 + (day === 11 ? 0.01 : 0),
      avg_response_time_ms: 2100 + n * 40,
      directive_version: day >= 9 ? 12 : 11,
      token_sketch: sketch(
        Math.round(med * 0.5),
        Math.round(med * 0.75),
        med,
        Math.round(med * 1.4),
        Math.round(med * (drift ? 1.95 : 1.7)),
      ),
      cluster_masses: clusters(
        Math.max(0.15, 0.52 - n * 0.03),
        Math.max(0.12, 0.33 - n * 0.01),
        Math.min(0.55, 0.15 + n * 0.04),
      ),
      // ADWIN fires on 02-09; alert window lands on 02-11
      adwin_change_point: day === 9,
    } satisfies FingerprintRow
  }),
]

export const AGENT_POLICY_SUPPORT: AgentDriftPolicy = {
  agent_id: "agt_01h9support",
  agent_name: "Support Agent",
  drift_action_stage: "shadow",
  drift_shadow_started_at: "2026-01-24T00:00:00.000Z",
  shadow_days_elapsed: 12,
  shadow_days_required: 30,
}

export const OPEN_DRIFT_COUNT = DRIFT_ALERT_LIST.filter(
  (a) => a.status === "open",
).length
