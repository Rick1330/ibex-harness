import { readFileSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

import { SURFACES, SURFACE_LIST, type SurfaceDefinition, type SurfaceKey } from "../shared/operator/surfaces"

const root = path.resolve(import.meta.dirname, "..")
const read = (relative: string): string => readFileSync(path.join(root, relative), "utf8")

const readme = read("README.md")
const ledger = read("../../engineering/architecture-v2/00-status-and-evidence.md")
const siteLedger = read("../../site/app/data/ledger.ts")
const siteStatus = read("../../site/content/docs/02.architecture/05.status-and-evidence.md")

const coreHeader = readme.indexOf("### Core tier")
const platformHeader = readme.indexOf("### Platform tier")

const entries = Object.entries(SURFACES) as [SurfaceKey, SurfaceDefinition][]

describe("surface status parity", () => {
  it("declares both tiers in the README", () => {
    expect(coreHeader).toBeGreaterThan(-1)
    expect(platformHeader).toBeGreaterThan(coreHeader)
  })

  it("keeps the surface count at the ADR-0089 inventory", () => {
    expect(SURFACE_LIST).toHaveLength(18)
    expect(SURFACE_LIST.filter((surface) => surface.tier === "core")).toHaveLength(10)
    expect(SURFACE_LIST.filter((surface) => surface.tier === "platform")).toHaveLength(8)
  })

  it("lists every surface once with a matching live/preview claim", () => {
    for (const [, surface] of entries) {
      const row = readme
        .split("\n")
        .find((line) => line.startsWith("|") && line.includes(`\`${surface.path}\``))

      expect(row, `${surface.label} is missing from the README surface table`).toBeDefined()

      const claimsLive = /Live D[12]/.test(row ?? "")
      expect(claimsLive, `${surface.label} status does not match SURFACES`).toBe(surface.availability === "live")
    }
  })

  it("places each surface in its declared tier", () => {
    for (const [, surface] of entries) {
      const row = readme
        .split("\n")
        .find((line) => line.startsWith("|") && line.includes(`\`${surface.path}\``))
      const rowIndex = row ? readme.indexOf(row) : -1

      if (surface.tier === "core") {
        expect(rowIndex, `${surface.label} must appear under Core tier`).toBeGreaterThan(coreHeader)
        expect(rowIndex, `${surface.label} must not appear under Platform tier`).toBeLessThan(platformHeader)
      } else {
        expect(rowIndex, `${surface.label} must appear under Platform tier`).toBeGreaterThan(platformHeader)
      }
    }
  })

  it("keeps live claims inside the D1/D2 evidence boundary", () => {
    const liveDomains = [...new Set(SURFACE_LIST.filter((surface) => surface.availability === "live").map((s) => s.domain))]
    expect(liveDomains.sort()).toEqual(["D1", "D2"])
  })

  it("keeps the ledgers aligned with the tier counts in SURFACES", () => {
    const core = SURFACE_LIST.filter((surface) => surface.tier === "core")
    const coreLive = core.filter((surface) => surface.availability === "live").length
    const corePreview = core.length - coreLive
    const platform = SURFACE_LIST.filter((surface) => surface.tier === "platform").length

    const sources: Array<[string, string]> = [
      ["engineering ledger", ledger],
      ["site ledger", siteLedger],
      ["site status page", siteStatus],
    ]

    for (const [name, text] of sources) {
      expect(text, `${name} must cite ADR-0089`).toContain("ADR-0089")
      expect(text, `${name} live count disagrees with SURFACES`).toContain(`${coreLive} of ${core.length} core surfaces`)
      expect(text, `${name} preview count disagrees with SURFACES`).toContain(`${corePreview} core surfaces`)
      expect(text, `${name} platform count disagrees with SURFACES`).toContain(`${platform} platform-tier surfaces`)
    }
  })
})
