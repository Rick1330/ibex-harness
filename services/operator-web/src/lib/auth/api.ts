import type {
  AuthEnvironment,
  BeginEnrollmentResult,
  LoginErrorCode,
  OperatorSession,
  SessionCookies,
  StepUpToken,
  TotpErrorCode,
} from "./types"

export class AuthApiError extends Error {
  code:
    | LoginErrorCode
    | TotpErrorCode
    | "INSUFFICIENT_PERMISSIONS"
    | "session_revoked"
  status: number
  constructor(code: AuthApiError["code"], message: string, status = 503) {
    super(message)
    this.name = "AuthApiError"
    this.code = code
    this.status = status
  }
}

const unavailable = () =>
  new AuthApiError(
    "auth_unavailable",
    "AuthService integration is not connected; no credentials were submitted.",
  )
export function getAuthEnvironment(): AuthEnvironment {
  const value = process.env.NEXT_PUBLIC_IBEX_ENV
  return value === "preview" || value === "staging" || value === "production"
    ? value
    : "local"
}
export function setAuthDemoFlags(_flags: {
  authDown?: boolean
  previewMissing?: boolean
}) {
  void _flags
}
export function loadSession(): {
  session: OperatorSession
  cookies: SessionCookies
} | null {
  return null
}
export function clearSession() {}
export function logout() {}
export async function issueOperatorSession(
  email: string,
  password: string,
): Promise<{ session: OperatorSession; cookies: SessionCookies }> {
  void email
  void password
  throw unavailable()
}
export async function registerOperatorOrg(input: {
  orgName: string
  email: string
  password: string
}): Promise<{ session: OperatorSession; cookies: SessionCookies }> {
  void input
  throw unavailable()
}
export async function refreshOperatorSession(
  csrfHeader: string,
): Promise<{ session: OperatorSession; cookies: SessionCookies }> {
  void csrfHeader
  throw unavailable()
}
export async function beginTotpEnrollment(): Promise<BeginEnrollmentResult> {
  throw unavailable()
}
export async function confirmTotpEnrollment(code: string): Promise<void> {
  void code
  throw unavailable()
}
export async function createStepUpToken(code: string): Promise<StepUpToken> {
  void code
  throw unavailable()
}
