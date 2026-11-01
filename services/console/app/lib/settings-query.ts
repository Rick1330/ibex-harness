import { SETTINGS_SECTIONS, isSettingsSection, type SettingsSection } from "@/lib/settings-preview"

export const SETTINGS_DEFAULT_SECTION: SettingsSection = "organization"

export function parseSettingsQuery(query: Record<string, unknown>): SettingsSection {
  const raw = Array.isArray(query.section) ? query.section[0] : query.section
  return typeof raw === "string" && isSettingsSection(raw) ? raw : SETTINGS_DEFAULT_SECTION
}

export function serializeSettingsQuery(section: SettingsSection): URLSearchParams {
  const params = new URLSearchParams()
  if (section !== SETTINGS_DEFAULT_SECTION) params.set("section", section)
  return params
}

export function settingsHref(section: SettingsSection): string {
  const query = serializeSettingsQuery(section).toString()
  return query ? `/settings?${query}` : "/settings"
}

export function nextSettingsSection(section: SettingsSection, delta: number): SettingsSection {
  const index = SETTINGS_SECTIONS.indexOf(section)
  return SETTINGS_SECTIONS[(index + delta + SETTINGS_SECTIONS.length) % SETTINGS_SECTIONS.length] ?? SETTINGS_DEFAULT_SECTION
}
