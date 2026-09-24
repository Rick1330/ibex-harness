/**
 * Fixture clients for Tokens / Provider Credentials / Webhooks APIs.
 * Shapes mirror completed 1.1.4 token management + org providers + webhooks.
 */

import type {
  CallerAuthz,
  PatToken,
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
