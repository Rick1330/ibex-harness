import { readFileSync, readdirSync, statSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

import { DEMO_FIXTURE_FILES, FIXTURE_MODULES, PREVIEW_FIXTURE_FILES } from "../app/lib/preview-fixtures"
import { SURFACES } from "../shared/operator/surfaces"

const root = path.resolve(import.meta.dirname, "..")
const libDir = path.join(root, "app/lib")
const read = (relative: string): string => readFileSync(path.join(root, relative), "utf8")
const readLib = (file: string): string => readFileSync(path.join(libDir, file), "utf8")

const SEEDED_DEV_ORG = "00000000-0000-0000-0000-000000000001"

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = path.join(dir, entry)
    return statSync(full).isDirectory() ? walk(full) : [full]
  })
}

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

  it("keeps preview fixtures out of live pages and the shared shell", () => {
    const productionShell = [
      "app/components/console/AppSidebar.vue",
      "app/components/console/ConsoleHeader.vue",
      "app/components/console/PreviewBanner.vue",
      "app/layouts/default.vue",
      "app/pages/index.vue",
      "app/pages/platform.vue",
      "app/pages/explore/index.vue",
      "app/pages/explore/t/[traceId].vue",
      "app/pages/explore/r/[runId].vue",
    ]

    const importers = walk(path.join(root, "app"))
      .filter((file) => file.endsWith(".vue") || file.endsWith(".ts"))
      .filter((file) => /@\/lib\/[a-z0-9-]+-preview"/.test(readFileSync(file, "utf8")))
      .map((file) => path.relative(root, file))

    for (const file of productionShell) {
      expect(importers, `${file} imports a preview fixture module`).not.toContain(file)
    }
  })

  it("renders a persistent preview banner above preview pages", () => {
    expect(read("app/layouts/default.vue")).toContain("<PreviewBanner />")
    expect(read("app/components/console/PreviewBanner.vue")).toContain("Illustrative preview")
  })
})
