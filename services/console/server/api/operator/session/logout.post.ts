import { defineEventHandler } from "h3"
import {
  appendSessionDeletionCookies,
  callOperatorSession,
  noStore,
  toHttpError,
} from "~~/server/utils/operator/http"

/**
 * Revoke the operator session and clear its cookies.
 *
 * The deletions are appended before the upstream call: the API's CSRF
 * middleware rejects a missing or mismatched token before its handler runs, so
 * an upstream failure would otherwise leave a valid session cookie in the
 * browser. Any upstream `Set-Cookie` headers are still relayed on top.
 */
export default defineEventHandler(async (event) => {
  noStore(event)
  appendSessionDeletionCookies(event)
  try {
    return await callOperatorSession(event, "logout")
  } catch (error) {
    toHttpError(error)
  }
})
