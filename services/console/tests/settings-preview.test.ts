import { describe, expect, it } from "vitest"

import {
  SETTINGS_CATEGORIES,
  SETTINGS_PRIVACY,
  SETTINGS_SECTIONS,
  firstSectionForCategory,
  isSettingsSection,
  nextSettingsCategory,
  settingsCategoryFor,
} from "../app/lib/settings-preview"

describe("settings release surface", () => {
  it("keeps only release-appropriate sections", () => {
    expect(SETTINGS_SECTIONS).not.toContain("security")
    expect(SETTINGS_SECTIONS).not.toContain("notifications")
    expect(SETTINGS_SECTIONS).not.toContain("integrations")
    expect(SETTINGS_SECTIONS).toContain("privacy")
  })

  it("maps every section to exactly one category", () => {
    for (const section of SETTINGS_SECTIONS) {
      const matches = SETTINGS_CATEGORIES.filter((category) =>
        (category.sections as readonly string[]).includes(section),
      )
      expect(matches, section).toHaveLength(1)
      expect(settingsCategoryFor(section)).toBe(matches[0]!.id)
      expect(isSettingsSection(section)).toBe(true)
    }
  })

  it("exposes capture, PII, and legal-hold rows without inventing a cloud control", () => {
    const labels = SETTINGS_PRIVACY.map((row) => row.label)
    expect(labels).toContain("Default capture mode")
    expect(labels).toContain("PII detection")
    expect(labels).toContain("Redaction threshold")
    expect(labels).toContain("Active legal holds")
    expect(labels).not.toContain("SIEM export")
    expect(labels).not.toContain("Slack alerts")
  })

  it("cycles categories and returns a valid first section", () => {
    const first = SETTINGS_CATEGORIES[0]!.id
    const last = SETTINGS_CATEGORIES[SETTINGS_CATEGORIES.length - 1]!.id
    expect(nextSettingsCategory(first, -1)).toBe(last)
    expect(nextSettingsCategory(last, 1)).toBe(first)
    for (const category of SETTINGS_CATEGORIES) {
      expect(isSettingsSection(firstSectionForCategory(category.id))).toBe(true)
    }
  })
})
