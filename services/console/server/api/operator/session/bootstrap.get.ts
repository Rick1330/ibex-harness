import { defineEventHandler } from "h3"
import { noStore, sessionBootstrap } from "~~/server/utils/operator/http"

/**
 * Non-secret session wiring the browser needs before it holds a session.
 *
 * The CSRF cookie name is deployment-configurable, so the logout page must not
 * assume `ibex_csrf`: with a non-default name it would send no `X-CSRF-Token`
 * and the API would reject the revocation before its handler runs. The token is
 * this browser's own double-submit value — the cookie is deliberately readable
 * by same-origin JavaScript, this response is same-origin only, and it is never
 * cached.
 */
export default defineEventHandler((event) => {
  noStore(event)
  return sessionBootstrap(event)
})
