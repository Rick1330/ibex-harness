/**
 * Drift Alerts (Phase 4.5 Intelligence Layer) — forward design against
 * ibex_core.drift_alerts / behavioral_fingerprints.
 *
 * Methodology reflected here is the *redesigned* stack (KS, ADWIN, JS
 * divergence, multi-centroid, Beta-Binomial) — not the original Gaussian
 * z-score walkthrough. Backend status: planned.
 */

export type DriftSeverity = "low" | "medium" | "high"

export type DriftAlertStatus =
  "open" | "acknowledged" | "resolved" | "false_positive"

export type DriftActionTaken = "logged" | "notified" | "suspended"

export type DriftActionStage = "shadow" | "notify" | "auto_suspend"

export type FeatureClass =
  | "token_quantile_sketch"
  | "tool_distribution_smoothed"
  | "response_cluster_centroids"
  | "error_successes"
  | "error_trials"

export type StatisticalTest =
  | "ks_two_sample"
  | "jensen_shannon"
  | "chi_squared_cluster"
  | "beta_binomial_ci"

/** Named quantiles for t-digest sketches (p10…p90). */
export type QuantileSketch = {
  p10: number
  p25: number
  p50: number
  p75: number
  p90: number
}

export type ToolMass = { tool: string; mass: number }

export type ClusterMass = { cluster: string; mass: number }

export type FeatureEvidence = {
  feature_class: FeatureClass
  test: StatisticalTest
  /** Persisted column — never collapse into a vague "drift score". */
  test_statistic: number
  /** Persisted column — show alongside statistic, not just pass/fail. */
  threshold_used: number
  /** Optional p-value / overlap credence when the test produces one. */
  p_value: number | null
  n_baseline: number
  n_current: number
  baseline_summary: string
  current_summary: string
  flagged: boolean
  /** t-digest / token sketch — distribution shape, not mean±std. */
  baseline_sketch: QuantileSketch | null
  current_sketch: QuantileSketch | null
  /** Smoothed tool categorical masses for JS divergence overlay. */
  baseline_tools: ToolMass[] | null
  current_tools: ToolMass[] | null
  /** Multi-centroid membership masses for χ² shift. */
  baseline_clusters: ClusterMass[] | null
  current_clusters: ClusterMass[] | null
  /** Beta–Binomial: successes / trials for error rate. */
  baseline_successes: number | null
  baseline_trials: number | null
  current_successes: number | null
  current_trials: number | null
}

export type DriftAlertListItem = {
  alert_id: string
  agent_id: string
  agent_name: string
  agent_slug: string
  severity: DriftSeverity
  status: DriftAlertStatus
  feature_classes: FeatureClass[]
  action_taken: DriftActionTaken
  drift_action_stage: DriftActionStage
  created_at: string
  /** When alert fired during a gradual directive rollout and forced rollback. */
  triggered_rollout_rollback: boolean
  rollback_directive_version: number | null
}

export type DriftAlertDetail = DriftAlertListItem & {
  org_id: string
  acknowledged_at: string | null
  acknowledged_by: string | null
  resolved_at: string | null
  resolution_notes: string | null
  evidence: FeatureEvidence[]
  contributing_trace_ids: string[]
  window_start: string
  window_end: string
  shadow_mode: boolean
  shadow_days_remaining: number | null
}

export type FingerprintRow = {
  fingerprint_id: string
  computed_at: string
  is_baseline: boolean
  avg_prompt_tokens: number
  tool_call_rate: number
  error_rate: number
  avg_response_time_ms: number
  directive_version: number | null
  /** t-digest token sketch for this window — shape, not a single mean. */
  token_sketch: QuantileSketch
  /** Multi-centroid membership for response clusters. */
  cluster_masses: ClusterMass[]
  /** ADWIN flagged a change point ending this window. */
  adwin_change_point: boolean
}

export type AgentDriftPolicy = {
  agent_id: string
  agent_name: string
  drift_action_stage: DriftActionStage
  drift_shadow_started_at: string
  shadow_days_elapsed: number
  shadow_days_required: number
}
