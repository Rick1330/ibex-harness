import { readFileSync, readdirSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

import { DEMO_FIXTURE_FILES, FIXTURE_MODULES, PREVIEW_FIXTURE_FILES } from "../app/lib/preview-fixtures"
import { PREVIEW_PAGES } from "../app/lib/preview-pages"
import { SURFACES, type SurfaceDefinition, type SurfaceKey } from "../shared/operator/surfaces"

const root = path.resolve(import.meta.dirname, "..")
const libDir = path.join(root, "app/lib")
const read = (relative: string): string => readFileSync(path.join(root, relative), "utf8")
const readLib = (file: string): string => readFileSync(path.join(libDir, file), "utf8")

const SEEDED_DEV_ORG = "00000000-0000-0000-0000-000000000001"

describe("preview fixture policy", () => {
  it("registers every preview fixture module", () => {
    const actual = readdirSync(libDir)
      .filter((file) => file.endsWith("-preview.ts"))
      .sort()
    expect(actual).toEqual([...PREVIEW_FIXTURE_FILES].sort())
  })

  it("maps every preview fixture module to a preview surface", () => {
    for (const module of FIXTURE_MODULES.filter((candidate) => candidate.kind === "preview")) {
      expect(SURFACES[module.surface].availability, `${module.file} maps to a live surface`).toBe("preview")
    }
  })

  it("uses only reserved tenant identifiers", () => {
    for (const file of [...PREVIEW_FIXTURE_FILES, ...DEMO_FIXTURE_FILES]) {
      const text = readLib(file)
      expect(text, `${file} uses a workspace-style tenant id`).not.toContain("org_ws_")
      expect(text, `${file} uses the seeded development org`).not.toContain(SEEDED_DEV_ORG)
    }
  })

  it("keeps demo mode compile-time and development-only", () => {
    expect(readLib("console-demo.ts")).toContain("export const CONSOLE_DEMO_ENABLED = import.meta.dev")
  })

  it("keeps preview fixtures out of live pages", () => {
    const livePages = [
      "app/pages/index.vue",
      "app/pages/platform.vue",
      "app/pages/explore/index.vue",
      "app/pages/explore/t/[traceId].vue",
      "app/pages/explore/r/[runId].vue",
    ]

    for (const page of livePages) {
      expect(read(page), `${page} imports a preview fixture module`).not.toMatch(/-preview"/)
    }
  })

  it("gives every preview surface an illustrative verdict and a 0% live claim", () => {
    for (const [key, surface] of Object.entries(SURFACES) as [SurfaceKey, SurfaceDefinition][]) {
      if (surface.availability !== "preview") continue

      const config = PREVIEW_PAGES[key]
      expect(config, `${surface.label} has no preview page config`).toBeDefined()
      expect(config?.verdict.toLowerCase(), `${surface.label} verdict is not marked illustrative`).toContain(
        "illustrative",
      )
      expect(config?.coverage, `${surface.label} coverage overclaims`).toContain("0% live")
    }
  })

  it("renders a persistent preview banner above preview pages", () => {
    expect(read("app/layouts/default.vue")).toContain("<PreviewBanner />")
    expect(read("app/components/console/PreviewBanner.vue")).toContain("Illustrative preview")
  })
})
