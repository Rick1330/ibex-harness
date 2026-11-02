import { readFileSync, readdirSync, statSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

import { SURFACES, type SurfaceKey } from "../shared/operator/surfaces"

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

/**
 * Component directories that back a surface, mapped to the surface they serve.
 *
 * The mapping is the point: if a surface flips to `live`, the test below fails
 * until its components leave this list, so a leftover fixture clock cannot ride
 * along with a live claim.
 */
const PREVIEW_DIRECTORIES: Array<{ root: string; surface: SurfaceKey }> = [
  { root: "components/console/access", surface: "access" },
  { root: "components/console/analytics", surface: "analytics" },
  { root: "components/console/audit", surface: "audit" },
  { root: "components/console/budget", surface: "budgets" },
  { root: "components/console/drift", surface: "drift" },
  { root: "components/console/incident", surface: "incidents" },
  { root: "components/console/policy", surface: "policies" },
  { root: "components/console/provider", surface: "providers" },
  { root: "components/console/settings", surface: "settings" },
  { root: "components/console/tool", surface: "mcp-tools" },
]

/** The fixture library itself, plus the shared component whose callers pass a clock. */
const FIXTURE_LIBRARY = [
  "lib/access-preview.ts",
  "lib/audit-preview.ts",
  "lib/govern-format.ts",
  "components/console/RelativeTime.vue",
]

const PREVIEW_ROOTS = [...PREVIEW_DIRECTORIES.map((entry) => entry.root), ...FIXTURE_LIBRARY]

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = path.join(dir, entry)
    return statSync(full).isDirectory() ? walk(full) : [full]
  })
}

/** POSIX separators, so the slash-separated allowlist matches on Windows too. */
function toPosix(relative: string): string {
  return relative.split(path.sep).join("/")
}

function isPreviewFile(relative: string): boolean {
  return PREVIEW_ROOTS.some((prefix) => relative === prefix || relative.startsWith(`${prefix}/`))
}

describe("console clock boundary", () => {
  it("keeps the fixture clock out of live components and pages", () => {
    const offenders = walk(appDir)
      .filter((file) => file.endsWith(".vue") || file.endsWith(".ts"))
      .map((file) => toPosix(path.relative(appDir, file)))
      .filter((relative) => !isPreviewFile(relative))
      .filter((relative) => readFileSync(path.join(appDir, relative), "utf8").includes("GOVERN_NOW"))

    expect(offenders, `these live files measure ages against the fixture clock: ${offenders.join(", ")}`).toEqual([])
  })

  it("maps every fixture-clock directory to a surface that is still preview", () => {
    for (const { root, surface } of PREVIEW_DIRECTORIES) {
      expect(
        SURFACES[surface].availability,
        `${root} is allowed the fixture clock, but ${surface} is no longer preview`,
      ).toBe("preview")
    }
  })

  it("requires an explicit clock in the shared relative-time component", () => {
    const source = readFileSync(path.join(appDir, "components/console/RelativeTime.vue"), "utf8")
    expect(source).toContain("now: number")
    expect(source).not.toContain("now?:")
  })
})
