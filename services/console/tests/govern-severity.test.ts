import { describe, expect, it } from "vitest"

import {
  GOVERN_SEVERITIES,
  GOVERN_SEVERITY_LABELS,
  GOVERN_SEVERITY_MEANING,
  compareGovernSeverity,
  isGovernSeverity,
  severityForDependency,
} from "../app/lib/govern-severity"

describe("govern severity vocabulary", () => {
  it("names all three severities in reading order, with a meaning for each", () => {
    expect(GOVERN_SEVERITIES).toEqual(["critical", "warning", "info"])
    expect(GOVERN_SEVERITIES.map((severity) => GOVERN_SEVERITY_LABELS[severity])).toEqual([
      "Critical",
      "Warning",
      "Info",
    ])
    const meanings = GOVERN_SEVERITIES.map((severity) => GOVERN_SEVERITY_MEANING[severity])
    expect(new Set(meanings).size).toBe(3)
    for (const meaning of meanings) expect(meaning.length).toBeGreaterThan(30)
  })

  it("orders findings by severity rather than by alphabetical label", () => {
    const rows = ["info", "critical", "warning"] as const
    expect([...rows].sort(compareGovernSeverity)).toEqual(["critical", "warning", "info"])
  })

  it("carries a dependency status into severity without inventing a fourth level", () => {
    expect(severityForDependency("unavailable")).toBe("critical")
    expect(severityForDependency("degraded")).toBe("warning")
    expect(severityForDependency("ok")).toBeNull()
  })

  it("accepts only the recorded vocabulary from a URL", () => {
    expect(isGovernSeverity("warning")).toBe(true)
    expect(isGovernSeverity("sev2")).toBe(false)
    expect(isGovernSeverity("Warning")).toBe(false)
  })
})
