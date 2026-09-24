/**
 * Directives, Routing, Experiments & Controlled Actions (4.D.5).
 *
 * Drift UI is explicitly deferred (F4-013 / Phase 4.5 producer) — do not
 * render drift score widgets on this page.
 *
 * Rollback: set CONTROLLED_ACTIONS_ENABLED false → preview/approval fail closed.
 */

export type DirectiveLifecycle =
  "draft" | "review" | "active" | "deprecated" | "revoked"

export type RegressionStatus =
  "passed" | "failed" | "critical_fail" | "pending" | "not_run"

export type RolloutStrategy = "immediate" | "new_sessions_only" | "gradual"

export type RolloutStage =
  | "dark_launch"
  | "shadow_1"
  | "pct_10"
  | "pct_25"
  | "pct_50"
  | "pct_100"
  | "paused"
  | "aborted"

export type BehaviorAssessment = "improvement" | "regression" | "neutral"

export type DirectiveListItem = {
  directive_id: string
  name: string
  agent: string
  status: DirectiveLifecycle
  active_version: number | null
  regression_status: RegressionStatus
  scenarios_passed: number
  scenarios_total: number
  last_promoted_by: string | null
  last_promoted_at: string | null
  rollout: {
    strategy: RolloutStrategy
    percentage: number
    stage: RolloutStage
    paused: boolean
  } | null
  owner: string
}

/** Immutable once created — only status transitions. */
export type DirectiveVersion = {
  version: number
  status: DirectiveLifecycle
  content_hash: string
  content_tokens: number
  content: string
  created_at: string
  created_by: string
  promoted_at: string | null
  promoted_by: string | null
  revoked_reason: string | null
  regression_status: RegressionStatus
  scenarios_passed: number
  scenarios_total: number
}

export type TextDiffHunk = {
  header: string
  lines: { op: " " | "+" | "-"; text: string }[]
}

export type TextDiff = {
  from_version: number
  to_version: number
  additions: number
  deletions: number
  token_delta: number
  hunks: TextDiffHunk[]
}

export type ScenarioDiff = {
  scenario_id: string
  name: string
  is_critical: boolean
  assessment: BehaviorAssessment
  before: string
  after: string
  run_id: string
  second_reviewer_required: boolean
  second_reviewer_signed: boolean
}

export type BehavioralDiff = {
  test_scenarios_run: number
  behavior_changed: number
  behavior_unchanged: number
  scenarios: ScenarioDiff[]
}

export type BlastRadius = {
  agents_affected: number
  sessions_affected: number
  strategy: RolloutStrategy
  dual_approval_required: boolean
  mfa_required: boolean
}

export type RolloutState = {
  target_version: number
  baseline_version: number
  strategy: RolloutStrategy
  percentage: number
  stage: RolloutStage
  stages: { id: RolloutStage; label: string; done: boolean; current: boolean }[]
  bake_remaining: string
  /** Guardrail signal — not Phase 4.5 drift fingerprint. */
  quality_signal: string
  paused: boolean
  auto_abort: {
    at: string
    reason: string
    rolled_back_to: number
    at_percentage: number
  } | null
}

export type RevokeResult = {
  affected_sessions: number
  sessions_transitioned_to_fallback: number
  fallback_version: number
}

export type RoutingCandidate = {
  provider: string
  model: string
  disposition: "selected" | "excluded"
  reason: string
}

export type RoutingProvenance = {
  request_id: string
  session_id: string
  capability_catalog_version: string
  credential_scope: string
  sticky_hash_bucket: number
  resolved_directive_version: number
  fallback_trigger: string | null
  candidates: RoutingCandidate[]
}

export type ExperimentArm = {
  arm_id: string
  label: string
  exposure_pct: number
}

export type ExperimentState = {
  experiment_id: string
  name: string
  status: "running" | "paused" | "killed" | "completed"
  assigned_arm: string
  exposure_at: string
  holdback: boolean
  arms: ExperimentArm[]
  guardrail_summary: string
}

export type LedgerActionKind =
  | "submit_review"
  | "promote"
  | "revoke"
  | "pause_rollout"
  | "resume_rollout"
  | "kill_experiment"
  | "auto_rollback"
  | "dual_approve"

export type ActionLedgerEntry = {
  id: string
  at: string
  actor: string
  kind: LedgerActionKind
  summary: string
  before_version: number | null
  after_version: number | null
  /** Idempotency key — duplicate submits share one entry. */
  idempotency_key: string
  reason?: string
}

export type DirectiveDetail = DirectiveListItem & {
  org: string
  description: string
  versions: DirectiveVersion[]
  /** Currently selected base→target for diff. */
  diff: TextDiff
  behavioral: BehavioralDiff
  blast_radius: BlastRadius
  rollout_live: RolloutState | null
  routing_sample: RoutingProvenance
  experiment: ExperimentState | null
  ledger: ActionLedgerEntry[]
  /** True when promote is blocked by regression gate. */
  promote_blocked_reason: string | null
}

/** Rollback: false → controlled actions fail closed. */
export const CONTROLLED_ACTIONS_ENABLED = true
