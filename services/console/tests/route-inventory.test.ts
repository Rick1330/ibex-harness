import { readdirSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

import inventory from "@/lib/route-classification.json"

const appRoot = fileURLToPath(new URL("../src/app", import.meta.url))

function pagePaths(directory: string, prefix = ""): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    if (!entry.isDirectory()) return entry.name === "page.tsx" ? [prefix || "/"] : []
    const segment = entry.name.replace(/^\[(.+)\]$/, ":$1")
    return pagePaths(`${directory}/${entry.name}`, `${prefix}/${segment}`)
  })
}

const actual = pagePaths(appRoot).sort()
const classified = Object.keys(inventory.routes)
  .filter((route) => route !== "/login" && route !== "/onboarding")
  .filter((route) => route === "/" || route === "/deferred" || route.startsWith("/dashboard"))
  .sort()

describe("Console route classification inventory", () => {
  it("classifies every page route and accounts for every implemented page", () => {
    expect(classified).toEqual(actual)
  })

  it("keeps only Overview fixture-previewable and D2 metadata routes live-backed", () => {
    const routes = inventory.routes as Record<string, { status: string; data_mode: string }>
    const liveD2Paths = new Set([
      "/dashboard/explore",
      "/dashboard/explore/t/:traceId",
      "/dashboard/explore/r/:runId",
    ])
    expect(routes["/dashboard"]).toMatchObject({ status: "preview-only", data_mode: "fixture" })
    for (const [path, entry] of Object.entries(routes)) {
      if (liveD2Paths.has(path)) {
        expect(entry, path).toMatchObject({ status: "implemented", data_mode: "none" })
        continue
      }
      if (path.startsWith("/dashboard/") && path !== "/dashboard") {
        expect(entry, path).toMatchObject({ status: "deferred", data_mode: "none" })
      }
    }
  })
})
