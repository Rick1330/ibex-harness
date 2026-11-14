import { describe, expect, it } from "vitest"

import { safeLoginNext } from "../app/lib/navigation"

describe("post-login return target", () => {
  it("keeps a same-origin application path, including its query", () => {
    expect(safeLoginNext("/")).toBe("/")
    expect(safeLoginNext("/explore?limit=10&status=ok")).toBe("/explore?limit=10&status=ok")
    expect(safeLoginNext("/memories/44444444-4444-4444-8444-444444444444")).toBe(
      "/memories/44444444-4444-4444-8444-444444444444",
    )
  })

  it("rejects absolute, protocol-relative, API, and auth paths", () => {
    expect(safeLoginNext("https://evil.example/steal")).toBe("/")
    expect(safeLoginNext("//evil.example/steal")).toBe("/")
    expect(safeLoginNext("javascript:alert(1)")).toBe("/")
    expect(safeLoginNext("/api/operator/overview")).toBe("/")
    expect(safeLoginNext("/login?next=/explore")).toBe("/")
    expect(safeLoginNext("/logout")).toBe("/")
    expect(safeLoginNext("/_nuxt/app.js")).toBe("/")
  })

  it("rejects traversal, control characters, and non-string values", () => {
    expect(safeLoginNext("/../../etc/passwd")).toBe("/")
    expect(safeLoginNext("/explore\n/evil")).toBe("/")
    expect(safeLoginNext(undefined)).toBe("/")
    expect(safeLoginNext(["//evil.example"])).toBe("/")
  })
})
