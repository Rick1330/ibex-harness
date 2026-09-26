import type {
  AuthEnvironment,
  OperatorSession,
  SessionCookies,
  StepUpToken,
} from "./types"

export class AuthApiError extends Error {
  code:
    | "INSUFFICIENT_PERMISSIONS"
    | "session_revoked"
    | "auth_unavailable"
  status: number
  constructor(code: AuthApiError["code"], message: string, status = 503) {
    super(message)
    this.name = "AuthApiError"
    this.code = code
    this.status = status
  }
}

const unavailable = (...context: unknown[]) => {
  if (context.length > 0) {
    // Inputs are intentionally not inspected: this adapter must never log credentials.
  }
  return new AuthApiError(
    "auth_unavailable",
    "AuthService integration is not connected; no credentials were submitted.",
  )
}

export function getAuthEnvironment(): AuthEnvironment {
  const value = process.env.NEXT_PUBLIC_IBEX_ENV
  return value === "preview" || value === "staging" || value === "production"
    ? value
    : "local"
}

export function setAuthDemoFlags(flags: {
  authDown?: boolean
  previewMissing?: boolean
}) {
  if (flags.authDown || flags.previewMissing) return
}

export function loadSession(): {
  session: OperatorSession
  cookies: SessionCookies
} | null {
  return null
}

export function clearSession(): void {
  return undefined
}

export function logout(): void {
  return undefined
}

export async function refreshOperatorSession(
  csrfHeader: string,
): Promise<{ session: OperatorSession; cookies: SessionCookies }> {
  throw unavailable(csrfHeader)
}

export async function createStepUpToken(code: string): Promise<StepUpToken> {
  throw unavailable(code)
}
