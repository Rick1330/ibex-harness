import { describe, expect, it } from "vitest"

import { operatorErrorMessage } from "../app/lib/operator-error"

const GENERIC_FALLBACK = "Sign-in failed. Try again."

describe("BFF error message reader", () => {
  it("surfaces a rejected PAT instead of the generic sign-in fallback", () => {
    // The shape `$fetch` actually sees. Nitro serialises the h3 error as
    // `{ statusCode, statusMessage, data: { error: { message } } }`, so the
    // stable envelope sits one level deeper than the old reader assumed.
    const fetchError = {
      statusCode: 401,
      data: {
        statusCode: 401,
        statusMessage: "That personal access token was not accepted.",
        stack: "",
        data: {
          error: {
            code: "INVALID_TOKEN",
            message: "That personal access token was not accepted.",
          },
        },
      },
    }

    const message = operatorErrorMessage(fetchError)

    expect(message).toBe("That personal access token was not accepted.")
    expect(message).not.toBe(GENERIC_FALLBACK)
  })

  it("reads a direct error envelope and a plain message body", () => {
    expect(operatorErrorMessage({ data: { error: { message: "Direct envelope" } } })).toBe(
      "Direct envelope",
    )
    expect(operatorErrorMessage({ data: { message: "Plain body" } })).toBe("Plain body")
  })

  it("returns null when no message is present so the page keeps its fallback", () => {
    expect(operatorErrorMessage(null)).toBeNull()
    expect(operatorErrorMessage(undefined)).toBeNull()
    expect(operatorErrorMessage({ data: {} })).toBeNull()
    expect(operatorErrorMessage({ data: { data: { error: { message: "" } } } })).toBeNull()
  })
})
