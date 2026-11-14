import { describe, expect, it } from "vitest"

import { applyOperatorResponse } from "../app/composables/useOperatorData"

function operatorResponse(
  body: string,
  init: ResponseInit & { cookies?: string[] } = {},
): Response {
  const { cookies = [], ...responseInit } = init
  const headers = new Headers(responseInit.headers)
  for (const cookie of cookies) headers.append("set-cookie", cookie)
  return new Response(body, { ...responseInit, headers })
}

describe("applyOperatorResponse", () => {
  it("relays every Set-Cookie header the BFF route emitted", async () => {
    const appended: string[] = []
    const response = operatorResponse(JSON.stringify({ ok: true }), {
      cookies: [
        "ibex_session=fresh; Path=/; HttpOnly; Secure; SameSite=Lax",
        "ibex_csrf=token; Path=/; Secure; SameSite=Lax",
      ],
    })

    const body = await applyOperatorResponse<{ ok: boolean }>(response, (cookie) =>
      appended.push(cookie),
    )

    expect(appended).toEqual([
      "ibex_session=fresh; Path=/; HttpOnly; Secure; SameSite=Lax",
      "ibex_csrf=token; Path=/; Secure; SameSite=Lax",
    ])
    expect(body).toEqual({ ok: true })
  })

  it("appends nothing when the route set no cookie", async () => {
    const appended: string[] = []

    await applyOperatorResponse(operatorResponse(JSON.stringify({ ok: true })), (cookie) =>
      appended.push(cookie),
    )

    expect(appended).toEqual([])
  })

  it("reports the status code and parsed body on a 4xx so useAsyncData sees the failure", async () => {
    const envelope = { error: { code: "UNAUTHENTICATED", message: "Session expired" } }
    const response = operatorResponse(JSON.stringify(envelope), { status: 401 })

    await expect(applyOperatorResponse(response, () => {})).rejects.toMatchObject({
      statusCode: 401,
      status: 401,
      data: envelope,
    })
  })

  it("relays cookies before throwing on an error response", async () => {
    const appended: string[] = []
    const response = operatorResponse(JSON.stringify({ error: { code: "UNAVAILABLE" } }), {
      status: 503,
      cookies: ["ibex_session=; Path=/; Max-Age=0; HttpOnly"],
    })

    await expect(
      applyOperatorResponse(response, (cookie) => appended.push(cookie)),
    ).rejects.toMatchObject({ statusCode: 503 })

    expect(appended).toEqual(["ibex_session=; Path=/; Max-Age=0; HttpOnly"])
  })

  it("returns a non-JSON body instead of throwing", async () => {
    const body = await applyOperatorResponse<string>(operatorResponse("upstream down"), () => {})

    expect(body).toBe("upstream down")
  })
})
