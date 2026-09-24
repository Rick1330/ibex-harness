/**
 * Operator auth (ADR-0079) — RS256 session/refresh + TOTP step-up.
 *
 * Explicit non-goals: OIDC/ACR, org-switch-at-login, dual-approval UI,
 * preview-token issuer.
 */

export type AuthEnvironment = "local" | "preview" | "staging" | "production"

export type SessionCookies = {
  /** HttpOnly access JWT — simulated client-side for fixture UI. */
  ibex_session: string
  /** HttpOnly refresh JWT. */
  ibex_refresh: string
  /** Readable CSRF double-submit. */
  ibex_csrf: string
}

export type OperatorSession = {
  sub: string
  email: string
  org_id: string
  org_name: string
  /** Org policy requires MFA. */
  mfa_required: boolean
  /** User has confirmed TOTP enrollment. */
  totp_enrolled: boolean
  issued_at: string
  access_expires_at: string
  refresh_family_id: string
}

export type LoginErrorCode =
  | "invalid_credentials"
  | "auth_unavailable"
  | "login_rate_limited"
  | "api_unreachable"
  | "preview_api_missing"

export type TotpErrorCode =
  | "ErrTOTPInvalidCode"
  | "ErrTOTPAlreadyDone"
  | "ErrTOTPLockedOut"
  | "auth_unavailable"

export type StepUpErrorCode = "INSUFFICIENT_PERMISSIONS" | "auth_unavailable"

export type BeginEnrollmentResult = {
  otpauth_uri: string
  /** Manual entry secret (same as URI secret). */
  secret: string
}

export type StepUpToken = {
  token: string
  sub: string
  org_id: string
  expires_at: string
}

export type AuthShellBanner = null | {
  kind: "degraded" | "stale"
  message: string
}
