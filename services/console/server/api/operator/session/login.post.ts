import { createError, defineEventHandler, getHeader, getRequestURL } from "h3"
import {
  callOperatorSession,
  noStore,
  readJsonBodyCapped,
  toHttpError,
} from "~~/server/utils/operator/http"

const PAT_MIN_LENGTH = 8
const PAT_MAX_LENGTH = 4096
const MAX_LOGIN_BODY_BYTES = 8 * 1024

type LoginRequest = { pat?: unknown }

/**
 * Exchange a PAT for operator session cookies.
 *
 * The PAT is sent once, in the request body, to the operator API. It is never
 * logged, never written to a URL, and never returned to the browser. The API's
 * `Set-Cookie` headers are relayed to the Console origin; the upstream origin
 * never reaches the client.
 */
export default defineEventHandler(async (event) => {
  noStore(event)

  // Login has no prior CSRF token, so reject a cross-origin browser post here.
  // This is the same origin check the SSE route applies, and it blocks login
  // CSRF (signing a victim into an attacker-controlled session). A request that
  // omits `Origin` is still covered by the `application/json` requirement below:
  // a cross-site HTML form cannot send that content type without a preflight.
  const origin = getHeader(event, "origin")
  if (origin && origin !== getRequestURL(event).origin) {
    throw createError({
      statusCode: 403,
      statusMessage: "Request origin is not allowed",
      data: { error: { code: "ORIGIN_REJECTED", message: "Request origin is not allowed." } },
    })
  }

  // The route is unauthenticated, so the body cap must hold without trusting
  // `Content-Length`: a chunked request can omit it, and a declared length can
  // lie. `readJsonBodyCapped` rejects a missing/oversized length, requires
  // `application/json`, and counts the bytes it actually reads.
  const body = (await readJsonBodyCapped(event, MAX_LOGIN_BODY_BYTES)) as LoginRequest | null
  const pat = typeof body?.pat === "string" ? body.pat.trim() : ""
  if (pat.length < PAT_MIN_LENGTH || pat.length > PAT_MAX_LENGTH) {
    throw createError({
      statusCode: 400,
      statusMessage: "A personal access token is required",
      data: {
        error: {
          code: "INVALID_REQUEST",
          message: "A personal access token is required.",
        },
      },
    })
  }

  try {
    return await callOperatorSession(event, "login", { pat })
  } catch (error) {
    toHttpError(error, { login: true })
  }
})
