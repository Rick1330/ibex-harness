import type {
  OperatorDirectiveDetail,
  OperatorDirectiveSummary,
  OperatorDirectiveVersion,
} from "~~/shared/operator/contracts"

/**
 * Presentation helpers for the live Directives surface.
 *
 * The contract only carries metadata, so nothing here may imply that a version's
 * instruction text was read: `content_digest` is an identity prefix, and
 * `content_bytes` is a size.
 */

export const INJECTION_MODE_LABELS = {
  system_first: "System, before history",
  system_append: "System, after history",
  user_prepend: "Prepend to the user turn",
} as const

export type InjectionMode = keyof typeof INJECTION_MODE_LABELS

/** Versions the pointer can name, newest first, as the API returns them. */
export function versionByNumber(
  detail: OperatorDirectiveDetail,
  versionNum: number | null,
): OperatorDirectiveVersion | null {
  if (versionNum === null) return null
  return detail.versions.find((version) => version.version_num === versionNum) ?? null
}

/**
 * The version that served the most sessions in the window.
 *
 * A rollback is invisible in usage alone, so the UI shows this next to the live
 * pointer: "live now" and "most used" can legitimately differ.
 */
export function mostUsedVersion(
  detail: OperatorDirectiveDetail,
): { version_num: number; sessions: number } | null {
  if (!detail.usage.length) return null
  return [...detail.usage].sort((left, right) => right.sessions - left.sessions)[0] ?? null
}

/**
 * Sessions that ran while the pointer named a version other than the live one.
 *
 * This is the honest rollback signal: those sessions are not stale data, they
 * simply ran before the pointer moved.
 */
export function sessionsOffPointer(detail: OperatorDirectiveDetail): number {
  const live = detail.active_version_num
  // An inactive directive has no pointer, so nothing can be "off" it.
  if (live === null) return 0
  return detail.usage
    .filter((row) => row.version_num !== live)
    .reduce((sum, row) => sum + row.sessions, 0)
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const kib = bytes / 1024
  if (kib < 1024) return `${kib.toFixed(kib < 10 ? 1 : 0)} KiB`
  return `${(kib / 1024).toFixed(1)} MiB`
}

export function injectionModeLabel(mode: string): string {
  return INJECTION_MODE_LABELS[mode as InjectionMode] ?? mode
}

export function directiveStateLabel(directive: OperatorDirectiveSummary): string {
  if (!directive.is_active) return "Inactive"
  if (directive.active_version_num === null) return "Active, no version published"
  return `Live v${directive.active_version_num}`
}
