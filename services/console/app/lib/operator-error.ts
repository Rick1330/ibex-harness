type OperatorErrorBody = {
  code?: string
  error?: { code?: string }
}

type OperatorErrorLike = {
  data?: OperatorErrorBody & { data?: OperatorErrorBody }
} | null

export function operatorErrorCode(error: unknown): string | null {
  const candidate = error as OperatorErrorLike
  return (
    candidate?.data?.error?.code ??
    candidate?.data?.code ??
    candidate?.data?.data?.error?.code ??
    candidate?.data?.data?.code ??
    null
  )
}

/** A refused operator read a session change can or cannot resolve. */
export type OperatorAuthStatus = 401 | 403

/**
 * The status of a refusal that a session change may resolve, or null.
 *
 * 401 and 403 are one classification with two outcomes, and the remedy differs:
 * a 401 means there is no signed-in session and signing in fixes it; a 403 means
 * the session is signed in without this read's grant and signing in again does
 * not grant it. Every surface reads this one function so a 401 cannot be shown
 * as the 403 refusal — or the reverse — in a second copy of the rule.
 */
export function operatorAuthStatus(error: unknown): OperatorAuthStatus | null {
  const candidate = error as { statusCode?: number; status?: number } | null
  // `statusCode` first: ofetch puts the response status there, and the SSR path
  // in `useOperatorData` sets both fields to the same value.
  const outer = candidate?.statusCode
  if (outer === 401 || outer === 403) return outer
  const inner = candidate?.status
  if (inner === 401 || inner === 403) return inner
  return null
}

/** A 401/403 means the operator session cannot read this tenant — never a data gap. */
export function isOperatorAuthError(error: unknown): boolean {
  return operatorAuthStatus(error) !== null
}

export function operatorFailureDetail(error: unknown): string {
  switch (operatorErrorCode(error)) {
    case "API_ORIGIN_UNAVAILABLE":
    case "API_ORIGIN_INVALID":
    case "API_ORIGIN_INSECURE":
      return "The console is not connected to an operator API in this environment. Set the API origin for this deployment and try again."
    case "OPERATOR_API_UNREACHABLE":
    case "OPERATOR_API_UNAVAILABLE":
      return "The operator API could not be reached. Check the deployment connection and try again."
    case "INVALID_UPSTREAM_PAYLOAD":
      return "The operator API returned a response this console could not validate. No values are shown."
    default:
      return "The operator API did not return a verified snapshot."
  }
}

type OperatorMessageBody = {
  message?: unknown
  error?: { message?: unknown }
}

type OperatorMessageLike = {
  data?: OperatorMessageBody & { data?: OperatorMessageBody }
} | null

function asMessage(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null
}

/**
 * The human message from a BFF error response, or null when there is none.
 *
 * `$fetch` puts the parsed response body in `error.data`. Nitro serialises an
 * `h3` error as `{ statusCode, statusMessage, data: { error: { message } } }`,
 * so the stable envelope sits one level deeper than a raw body:
 * `error.data.data.error.message`. Reading only `error.data.error.message`
 * always misses, which is why the login page showed its generic fallback for
 * every rejection. Both shapes are read here.
 */
export function operatorErrorMessage(error: unknown): string | null {
  const body = (error as OperatorMessageLike)?.data
  // The stable envelope first; the h3 body fields are fallbacks for a route
  // that throws without `data`.
  return (
    asMessage(body?.data?.error?.message) ??
    asMessage(body?.error?.message) ??
    asMessage(body?.data?.message) ??
    asMessage(body?.message)
  )
}
