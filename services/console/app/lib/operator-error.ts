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

/** A 401/403 means the operator session cannot read this tenant — never a data gap. */
export function isOperatorAuthError(error: unknown): boolean {
  const status = (error as { statusCode?: number; status?: number } | null)?.statusCode
  if (status === 401 || status === 403) return true
  const inner = (error as { status?: number } | null)?.status
  return inner === 401 || inner === 403
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
