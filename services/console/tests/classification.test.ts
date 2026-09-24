import { describe, expect, it } from "vitest"
import {
  classifyPath,
  isDashboardPreviewEnabled,
  isPreviewEnabled,
  resolveDashboardBoundary,
  resolveDataMode,
} from "@/lib/classification"
import { getPreviewFixture } from "@/lib/preview-fixtures"

describe("console data boundary", () => {
  it("defaults to production and never enables preview implicitly", () => {
    expect(resolveDataMode({})).toBe("production")
    expect(resolveDataMode({ CONSOLE_DATA_MODE: "preview" })).toBe("production")
    expect(
      resolveDataMode({
        CONSOLE_DATA_MODE: "preview",
        CONSOLE_PREVIEW: "1",
      }),
    ).toBe("preview")
    expect(
      resolveDataMode({
        NODE_ENV: "production",
        CONSOLE_DATA_MODE: "preview",
        CONSOLE_PREVIEW: "1",
      }),
    ).toBe("production")
    expect(
      isPreviewEnabled({
        NODE_ENV: "production",
        CONSOLE_DATA_MODE: "test",
      }),
    ).toBe(false)
    expect(
      isDashboardPreviewEnabled({
        NODE_ENV: "production",
        NEXT_PUBLIC_CONSOLE_PREVIEW: "1",
        CONSOLE_DATA_MODE: "preview",
        CONSOLE_PREVIEW: "1",
      }),
    ).toBe(false)
  })

  it("requires both server preview variables and the public presentation flag", () => {
    const serverPreview = {
      NEXT_PUBLIC_CONSOLE_PREVIEW: "1",
      CONSOLE_DATA_MODE: "preview",
      CONSOLE_PREVIEW: "1",
    }
    expect(isDashboardPreviewEnabled(serverPreview)).toBe(true)
    expect(
      isDashboardPreviewEnabled({
        ...serverPreview,
        CONSOLE_PREVIEW: "0",
      }),
    ).toBe(false)
    expect(
      isDashboardPreviewEnabled({
        ...serverPreview,
        NEXT_PUBLIC_CONSOLE_PREVIEW: "0",
      }),
    ).toBe(false)
  })

  it.each([
    [{}, "unavailable"],
    [{ CONSOLE_DATA_MODE: "preview" }, "unavailable"],
    [{ CONSOLE_PREVIEW: "1" }, "unavailable"],
    [{ CONSOLE_DATA_MODE: "preview", CONSOLE_PREVIEW: "1" }, "unavailable"],
    [
      {
        NEXT_PUBLIC_CONSOLE_PREVIEW: "1",
        CONSOLE_DATA_MODE: "preview",
        CONSOLE_PREVIEW: "1",
      },
      "preview",
    ],
    [
      {
        NODE_ENV: "production",
        NEXT_PUBLIC_CONSOLE_PREVIEW: "1",
        CONSOLE_DATA_MODE: "preview",
        CONSOLE_PREVIEW: "1",
      },
      "unavailable",
    ],
  ] as const)("resolves %s as %s", (env, expected) => {
    expect(resolveDashboardBoundary(env)).toBe(expected)
  })

  it("rejects preview fixtures in production mode", () => {
    expect(() => getPreviewFixture("production")).toThrow(
      "PREVIEW_FIXTURES_DISABLED_IN_PRODUCTION",
    )
    expect(getPreviewFixture("test").label).toBe("TEST DATA")
  })
})

describe("console route classification", () => {
  it("keeps D0 overview preview-only and later surfaces deferred", () => {
    expect(classifyPath("/dashboard").status).toBe("preview-only")
    expect(classifyPath("/dashboard/explore").status).toBe("deferred")
    expect(classifyPath("/dashboard/analytics").status).toBe("deferred")
    expect(classifyPath("/dashboard/settings").status).toBe("deferred")
    expect(classifyPath("/login").status).toBe("specified-not-implemented")
    expect(classifyPath("/onboarding").status).toBe("specified-not-implemented")
  })
})
