import { describe, expect, it } from "vitest"

import { isOperatorAuthError, operatorAuthStatus } from "../app/lib/operator-error"

/**
 * One classification, two outcomes.
 *
 * The Console renders a different remedy for a 401 (no session: sign in) and a
 * 403 (signed in without the grant: sign-in cannot help). Both `operatorAuthStatus`
 * and `isOperatorAuthError` must therefore agree on the same set of errors, with
 * the status preserved rather than flattened to a boolean.
 */
describe("operator refusal classification", () => {
  it("returns the status, so 401 and 403 stay distinguishable", () => {
    expect(operatorAuthStatus({ statusCode: 401 })).toBe(401)
    expect(operatorAuthStatus({ statusCode: 403 })).toBe(403)
  })

  it("reads the inner status when a caller only carries `status`", () => {
    expect(operatorAuthStatus({ status: 401 })).toBe(401)
    expect(operatorAuthStatus({ status: 403 })).toBe(403)
  })

  it("returns null for anything a session change cannot resolve", () => {
    for (const error of [
      null,
      undefined,
      {},
      new Error("boom"),
      { statusCode: 500 },
      { statusCode: 502, status: 502 },
      { statusCode: 429 },
    ]) {
      expect(operatorAuthStatus(error)).toBeNull()
    }
  })

  it("keeps the boolean helper as the same classification", () => {
    for (const error of [
      { statusCode: 401 },
      { statusCode: 403 },
      { status: 401 },
      { status: 403 },
    ]) {
      expect(isOperatorAuthError(error)).toBe(true)
    }
    for (const error of [null, undefined, {}, { statusCode: 500 }, { status: 503 }]) {
      expect(isOperatorAuthError(error)).toBe(false)
    }
  })
})
