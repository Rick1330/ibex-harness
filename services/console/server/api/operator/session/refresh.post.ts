import { callOperatorSession, noStore, toHttpError } from "~~/server/utils/operator/http"

/**
 * Rotate the access cookie using the refresh cookie. The API decides rotation
 * and revocation; this route only forwards the known session cookies, the CSRF
 * header, and the browser's origin, then relays `Set-Cookie` verbatim.
 */
export default defineEventHandler(async (event) => {
  noStore(event)
  try {
    return await callOperatorSession(event, "refresh")
  } catch (error) {
    toHttpError(error)
  }
})
