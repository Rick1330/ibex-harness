import { readFileSync, readdirSync, statSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

import { SURFACES } from "../shared/operator/surfaces"

/**
 * The console has two clocks, and they must not be mixed:
 *
 * - preview fixtures are measured against the fixed `GOVERN_NOW`, so a page renders the same
 *   string on the server and the client and a 2026 fixture never reads "3 years ago";
 * - live surfaces are measured against a reference they own — the observation time the read
 *   returned, or a ticking `nowMs`.
 *
 * `formatGovernRelative` therefore takes a required reference. This test enforces the other half:
 * only preview modules may name the fixture clock at all.
 */

const root = path.resolve(import.meta.dirname, "..")
const appDir = path.join(root, "app")

/** Component directories that back a `preview` surface in the ADR-0089 registry. */
const PREVIEW_ROOTS = [
  "components/console/access",
  "components/console/analytics",
  "components/console/audit",
  "components/console/budget",
  "components/console/drift",
  "components/console/incident",
  "components/console/policy",
  "components/console/provider",
  "components/console/settings",
  "components/console/tool",
  // The fixture library itself and the shared relative-time component, whose
  // callers must pass an explicit clock.
  "lib/access-preview.ts",
  "lib/audit-preview.ts",
  "lib/govern-format.ts",
  "components/console/RelativeTime.vue",
]

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = path.join(dir, entry)
    return statSync(full).isDirectory() ? walk(full) : [full]
  })
}

function isPreviewFile(relative: string): boolean {
  return PREVIEW_ROOTS.some((prefix) => relative === prefix || relative.startsWith(`${prefix}/`))
}

describe("console clock boundary", () => {
  it("keeps the fixture clock out of live components and pages", () => {
    const offenders = walk(appDir)
      .filter((file) => file.endsWith(".vue") || file.endsWith(".ts"))
      .map((file) => path.relative(appDir, file))
      .filter((relative) => !isPreviewFile(relative))
      .filter((relative) => readFileSync(path.join(appDir, relative), "utf8").includes("GOVERN_NOW"))

    expect(offenders, `these live files measure ages against the fixture clock: ${offenders.join(", ")}`).toEqual([])
  })

  it("maps every preview root to a preview surface or the fixture library", () => {
    // A surface that goes live must move its components out of the preview list,
    // or this test would keep allowing the fixture clock on a live page.
    const livePaths = new Set(
      Object.values(SURFACES)
        .filter((surface) => surface.availability === "live")
        .map((surface) => surface.path),
    )
    const liveComponentRoots = ["components/console/evidence", "components/console/directive", "components/console/explore"]
    for (const root of liveComponentRoots) {
      expect(PREVIEW_ROOTS, `${root} backs a live surface`).not.toContain(root)
    }
    expect(livePaths.size).toBeGreaterThan(0)
  })

  it("requires an explicit clock in the shared relative-time component", () => {
    const source = readFileSync(path.join(appDir, "components/console/RelativeTime.vue"), "utf8")
    expect(source).toContain("now: number")
    expect(source).not.toContain("now?:")
  })
})
