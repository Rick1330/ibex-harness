/**
 * Settings / Org v2 — organizations.settings JSONB, ADR-0009 bitmap,
 * 4.P.3 privacy/legal-hold (status: done), PATs, providers, webhooks, audit.
 */

import type { OrgQuotaSnapshot } from "@/lib/org/tier"

export type MemberRole = "owner" | "admin" | "member" | "viewer"
export type MemberStatus = "active" | "invited" | "suspended" | "deactivated"

export type GateBlock =
  | { kind: "feature_flag"; flag: string }
  | { kind: "kill_switch"; switch: string }
  | { kind: "permission"; bit: string }
  | { kind: "step_up" }
  | { kind: "tier"; feature: string }
  | null

export type OrgSettingsJsonb = {
  mfa_required: boolean
  ip_allowlist: string[]
  sso_domain: string | null
  data_retention_days: number
  memory_extraction_enabled: boolean
  drift_detection_enabled: boolean
  federation_enabled: boolean
}

export type EmbeddingProfile = {
  profile: "cpu" | "gpu" | "hosted"
  dimension: number
  model_id: string
}

export type OrgMember = {
  user_id: string
  name: string
  email: string
  role: MemberRole
  status: MemberStatus
  last_login_at: string | null
  last_login_ip: string | null
  mfa_enabled: boolean
  failed_login_attempts: number
  locked_until: string | null
  sso_provider: string | null
  sso_subject: string | null
}

export type ActiveSession = {
  session_id: string
  device: string
  ip: string
  last_seen_at: string
  current: boolean
}

export type PatToken = {
  token_id: string
  name: string
  prefix: string
  permissions: string[]
  created_at: string
  /** Owner — own-token revoke always allowed; others need TokenRevoke. */
  owner_user_id: string
  expires_at: string | null
  is_revoked: boolean
  revoked_at: string | null
  agent_id: string | null
  /**
   * Syntax-validated only — not persisted/enforced yet.
   * Omit from create UI or label "coming soon"; never imply CIDR allowlisting is active.
   */
  allowed_ips_coming_soon: string[]
}

export type PermissionPickerBit = {
  bit: number
  wire: string
  name: string
  group: "Memory" | "Directive" | "Session" | "Trace" | "Admin" | "Federation"
  requires_mfa: boolean
}

export type ProviderCredential = {
  provider_id: string
  provider_name: string
  status: "active" | "invalid" | "rotating"
  key_hint: string
  base_url: string | null
  last_validated_at: string | null
}

export type WebhookEndpoint = {
  webhook_id: string
  url: string
  events: string[]
  status: "active" | "disabled"
  /** Hint only — secret never re-fetched. */
  secret_set: boolean
  secret_hint: string
  agent_ids: string[]
  created_at: string
}

export type LegalHold = {
  hold_id: string
  reason: string
  created_at: string
  created_by: string
  active: boolean
}

export type CapturePolicy = {
  category: string
  mode: "metadata_only" | "full" | "off"
  explanation: string
}

export type DeletionStoreReceipt = {
  store: "postgres" | "clickhouse" | "redis" | "object_store"
  status: "verified" | "not_applicable" | "store_unreachable"
}

export type AuditClassification =
  "public" | "internal" | "confidential" | "restricted"

export type AuditActorKind = "user" | "token" | "service"

/**
 * Unified timeline row — audit_log always; operator_action_ledger fields
 * present only for high-impact actions (preview_token, dual-approval).
 */
export type AuditEntry = {
  entry_id: string
  at: string
  actor: string
  actor_kind: AuditActorKind
  /** Service account label when actor_kind === "service". */
  service_name: string | null
  action: string
  resource_type: string
  resource_id: string
  /** False when resource deleted / inaccessible — render plain text, not a link. */
  resource_linkable: boolean
  ip: string
  user_agent: string | null
  request_id: string | null
  trace_id: string | null
  success: boolean
  error_code: string | null
  error_message: string | null
  data_classification: AuditClassification
  previous_state: Record<string, unknown> | null
  new_state: Record<string, unknown> | null
  /** Ledger: step-up verified for this action. */
  step_up_verified: boolean
  step_up_jti: string | null
  preview_token: string | null
  idempotency_key: string | null
  requires_second_actor: boolean
  second_actor_user_id: string | null
  second_actor_email: string | null
  second_actor_at: string | null
}

export type CallerAuthz = {
  role: MemberRole
  bits: string[]
  feature_flags: Record<string, boolean>
  kill_switches: Record<string, boolean>
  step_up_active: boolean
  step_up_expires_at: string | null
}

export type SettingsPageV2 = {
  org: OrgQuotaSnapshot
  settings: OrgSettingsJsonb
  embedding: EmbeddingProfile
  members: OrgMember[]
  sessions: ActiveSession[]
  tokens: PatToken[]
  permission_picker: PermissionPickerBit[]
  providers: ProviderCredential[]
  webhooks: WebhookEndpoint[]
  legal_holds: LegalHold[]
  capture_policies: CapturePolicy[]
  deletion_demo_receipts: DeletionStoreReceipt[]
  audit: AuditEntry[]
  caller: CallerAuthz
  /** Known residual — ClickHouse TTL under hold (#853). */
  residual_ch_ttl_under_hold: true
}
