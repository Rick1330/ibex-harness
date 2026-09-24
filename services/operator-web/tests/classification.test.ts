import { describe, expect, it } from "vitest"
import {
  classifyPath,
  isDashboardPreviewEnabled,
  isPreviewEnabled,
  resolveDataMode,
} from "@/lib/classification"
import { getPreviewFixture } from "@/lib/preview-fixtures"

describe("operator-web data boundary", () => {
  it("defaults to production and never enables preview implicitly", () => {
    expect(resolveDataMode({})).toBe("production")
    expect(resolveDataMode({ OPERATOR_WEB_DATA_MODE: "preview" })).toBe(
      "production",
    )
    expect(
      resolveDataMode({
        OPERATOR_WEB_DATA_MODE: "preview",
        OPERATOR_WEB_PREVIEW: "1",
      }),
    ).toBe("preview")
    expect(
      resolveDataMode({
        NODE_ENV: "production",
        OPERATOR_WEB_DATA_MODE: "preview",
        OPERATOR_WEB_PREVIEW: "1",
      }),
    ).toBe("production")
    expect(
      isPreviewEnabled({
        NODE_ENV: "production",
        OPERATOR_WEB_DATA_MODE: "test",
      }),
    ).toBe(false)
    expect(
      isDashboardPreviewEnabled({
        NODE_ENV: "production",
        NEXT_PUBLIC_OPERATOR_WEB_PREVIEW: "1",
        OPERATOR_WEB_DATA_MODE: "preview",
        OPERATOR_WEB_PREVIEW: "1",
      }),
    ).toBe(false)
  })

  it("requires both server preview variables and the public presentation flag", () => {
    const serverPreview = {
      NEXT_PUBLIC_OPERATOR_WEB_PREVIEW: "1",
      OPERATOR_WEB_DATA_MODE: "preview",
      OPERATOR_WEB_PREVIEW: "1",
    }
    expect(isDashboardPreviewEnabled(serverPreview)).toBe(true)
    expect(
      isDashboardPreviewEnabled({
        ...serverPreview,
        OPERATOR_WEB_PREVIEW: "0",
      }),
    ).toBe(false)
    expect(
      isDashboardPreviewEnabled({
        ...serverPreview,
        NEXT_PUBLIC_OPERATOR_WEB_PREVIEW: "0",
      }),
    ).toBe(false)
  })

  it("rejects preview fixtures in production mode", () => {
    expect(() => getPreviewFixture("production")).toThrow(
      "PREVIEW_FIXTURES_DISABLED_IN_PRODUCTION",
    )
    expect(getPreviewFixture("test").label).toBe("TEST DATA")
  })
})

describe("operator-web route classification", () => {
  it("keeps D0 overview preview-only and later surfaces deferred", () => {
    expect(classifyPath("/dashboard").status).toBe("preview-only")
    expect(classifyPath("/dashboard/explore").status).toBe("deferred")
    expect(classifyPath("/dashboard/analytics").status).toBe("deferred")
    expect(classifyPath("/dashboard/settings").status).toBe("deferred")
    expect(classifyPath("/login").status).toBe("specified-not-implemented")
    expect(classifyPath("/onboarding").status).toBe("specified-not-implemented")
  })
})
