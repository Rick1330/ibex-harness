/**
 * Fixture clients for Tokens / Provider Credentials / Webhooks APIs.
 * Shapes mirror completed 1.1.4 token management + org providers + webhooks.
 */

import { AGENT_STORE } from "@/lib/agents/fixtures"
import type {
  CallerAuthz,
  PatToken,
  PermissionPickerBit,
  ProviderCredential,
  WebhookEndpoint,
} from "./types"

function delay(ms = 240) {
  return new Promise((r) => window.setTimeout(r, ms))
}

export class SettingsApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

/** Identical not-found for missing and cross-tenant — never leak existence. */
export function notFoundToken(): never {
  throw new SettingsApiError(404, "NOT_FOUND", "Token not found")
}

export type CreateTokenInput = {
  name: string
  permissions: string[]
  expires_at: string | null
  agent_id: string | null
}

export type CreateTokenResult = {
  token: PatToken
  /** Shown exactly once — never re-fetched. */
  plaintext: string
}

export async function createPatToken(
  input: CreateTokenInput,
  opts: {
    caller: CallerAuthz
    picker: PermissionPickerBit[]
    ownerUserId: string
  },
): Promise<CreateTokenResult> {
  await delay()
  if (!opts.caller.bits.includes("TokenCreate")) {
    throw new SettingsApiError(
      403,
      "FORBIDDEN",
      "Missing permission: TokenCreate",
    )
  }
  if (!input.name.trim()) {
    throw new SettingsApiError(400, "INVALID", "Name required")
  }
  if (input.permissions.length === 0) {
    throw new SettingsApiError(400, "INVALID", "Select at least one permission")
  }
  for (const wire of input.permissions) {
    const bit = opts.picker.find((p) => p.wire === wire)
    if (!bit || !opts.caller.bits.includes(bit.name)) {
      throw new SettingsApiError(
        403,
        "PERMISSION_ELEVATION_DENIED",
        "Cannot grant permissions you do not hold",
      )
    }
  }
  if (input.agent_id) {
    const exists = AGENT_STORE.some((a) => a.agent_id === input.agent_id)
    if (!exists) {
      throw new SettingsApiError(400, "INVALID", "Unknown agent_id")
    }
  }
  const uuid = crypto.randomUUID().replace(/-/g, "")
  const secret =
    crypto.randomUUID().replace(/-/g, "") + crypto.randomUUID().replace(/-/g, "")
  const plaintext = `ibex_pat_${uuid}_${secret}`
  const now = new Date().toISOString()
  const token: PatToken = {
    token_id: `tok_${crypto.randomUUID().replace(/-/g, "").slice(0, 8)}`,
    name: input.name.trim(),
    prefix: `ibex_pat_${uuid.slice(0, 4)}`,
    permissions: input.permissions,
    created_at: now,
    owner_user_id: opts.ownerUserId,
    expires_at: input.expires_at,
    is_revoked: false,
    revoked_at: null,
    agent_id: input.agent_id,
    allowed_ips_coming_soon: [],
  }
  return { token, plaintext }
}

export async function revokePatToken(
  token: PatToken,
  opts: { caller: CallerAuthz; callerUserId: string },
): Promise<PatToken> {
  await delay(180)
  // Cross-tenant / missing → identical 404 (caller never sees distinguishing UI).
  if (!token) notFoundToken()
  const isOwn = token.owner_user_id === opts.callerUserId
  if (!isOwn && !opts.caller.bits.includes("TokenRevoke")) {
    throw new SettingsApiError(
      403,
      "FORBIDDEN",
      "Missing permission: TokenRevoke",
    )
  }
  return {
    ...token,
    is_revoked: true,
    revoked_at: new Date().toISOString(),
  }
}

export type UpsertProviderInput = {
  provider_name: string
  api_key: string
  base_url?: string | null
}

export async function upsertProviderCredential(
  input: UpsertProviderInput,
  opts: { caller: CallerAuthz; existing?: ProviderCredential | null },
): Promise<ProviderCredential> {
  await delay(320)
  if (!opts.caller.bits.includes("OrgSettingsWrite")) {
    throw new SettingsApiError(
      403,
      "FORBIDDEN",
      "Missing permission: OrgSettingsWrite",
    )
  }
  const key = input.api_key.trim()
  if (key.length < 8) {
    throw new SettingsApiError(400, "INVALID", "API key too short")
  }
  // Fixture "validation": keys starting with "bad" fail upstream validation.
  const invalid = key.toLowerCase().startsWith("bad")
  const now = new Date().toISOString()
  return {
    provider_id: opts.existing?.provider_id ?? `prov_${Date.now()}`,
    provider_name: input.provider_name,
    status: invalid ? "invalid" : "active",
    key_hint: `****${key.slice(-4)}`,
    base_url: input.base_url ?? null,
    last_validated_at: now,
  }
}

export async function removeProviderCredential(
  _providerId: string,
  opts: { caller: CallerAuthz },
): Promise<void> {
  await delay(180)
  if (!opts.caller.bits.includes("OrgSettingsWrite")) {
    throw new SettingsApiError(
      403,
      "FORBIDDEN",
      "Missing permission: OrgSettingsWrite",
    )
  }
}

export type CreateWebhookInput = {
  url: string
  events: string[]
  agent_ids?: string[]
}

export type CreateWebhookResult = {
  webhook: WebhookEndpoint
  /** Signing secret — shown once. */
  secret: string
}

export async function createWebhookEndpoint(
  input: CreateWebhookInput,
  opts: { caller: CallerAuthz },
): Promise<CreateWebhookResult> {
  await delay(300)
  if (!opts.caller.bits.includes("TokenCreate")) {
    throw new SettingsApiError(
      403,
      "FORBIDDEN",
      "Missing permission: TokenCreate",
    )
  }
  let url: URL
  try {
    url = new URL(input.url.trim())
  } catch {
    throw new SettingsApiError(400, "INVALID", "Enter a valid HTTPS URL")
  }
  if (url.protocol !== "https:") {
    throw new SettingsApiError(400, "INVALID", "Webhook URL must be HTTPS")
  }
  if (input.events.length === 0) {
    throw new SettingsApiError(400, "INVALID", "Select at least one event")
  }
  const secret = `whsec_${crypto.randomUUID().replace(/-/g, "")}${crypto.randomUUID().replace(/-/g, "")}`
  const webhook: WebhookEndpoint = {
    webhook_id: `wh_${crypto.randomUUID().replace(/-/g, "").slice(0, 6)}`,
    url: url.toString(),
    events: input.events,
    status: "active",
    secret_set: true,
    secret_hint: `${secret.slice(0, 8)}…`,
    agent_ids: input.agent_ids ?? [],
    created_at: new Date().toISOString(),
  }
  return { webhook, secret }
}

export async function rotateWebhookSecret(
  webhook: WebhookEndpoint,
  opts: { caller: CallerAuthz },
): Promise<{ webhook: WebhookEndpoint; secret: string }> {
  await delay(220)
  if (!opts.caller.bits.includes("TokenCreate")) {
    throw new SettingsApiError(
      403,
      "FORBIDDEN",
      "Missing permission: TokenCreate",
    )
  }
  const secret = `whsec_${crypto.randomUUID().replace(/-/g, "")}${crypto.randomUUID().replace(/-/g, "")}`
  return {
    webhook: {
      ...webhook,
      secret_set: true,
      secret_hint: `${secret.slice(0, 8)}…`,
    },
    secret,
  }
}

export function tokenStatus(
  t: PatToken,
  now = Date.now(),
): "active" | "revoked" | "expired" {
  if (t.is_revoked) return "revoked"
  if (t.expires_at && Date.parse(t.expires_at) < now) return "expired"
  return "active"
}

export function relativeValidated(iso: string | null): string {
  if (!iso) return "never validated"
  const ms = Date.now() - Date.parse(iso)
  if (Number.isNaN(ms)) return "—"
  const h = Math.floor(ms / 3_600_000)
  if (h < 1) return "validated just now"
  if (h < 48) return `validated ${h}h ago`
  return `validated ${Math.floor(h / 24)}d ago`
}
