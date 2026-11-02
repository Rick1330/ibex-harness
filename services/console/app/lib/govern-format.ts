/** Fixed clock keeps relative ages stable across server and client rendering. */
export const GOVERN_NOW = Date.parse("2026-10-30T15:12:00Z")

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

function toTime(value: string | null | undefined): number | null {
  if (!value) return null
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : null
}

/**
 * Relative age for a recorded timestamp.
 *
 * Fixtures are measured against the fixed `GOVERN_NOW` so server and client
 * render the same string. A live surface passes its own reference (the
 * observation time it just read) — measuring live data against a fixed clock
 * would report a record from today as "just now" for as long as the constant
 * is not moved.
 */
export function formatGovernRelative(
  value: string | null | undefined,
  reference: string | null | undefined = null,
): string {
  const time = toTime(value)
  if (time === null) return "Not recorded"
  const referenceTime = reference ? (toTime(reference) ?? GOVERN_NOW) : GOVERN_NOW
  const delta = referenceTime - time
  if (delta < 0) return "after the read window"
  if (delta < MINUTE) return "just now"
  if (delta < HOUR) return `${Math.floor(delta / MINUTE)}m ago`
  if (delta < DAY) return `${Math.floor(delta / HOUR)}h ago`
  if (delta < 30 * DAY) return `${Math.floor(delta / DAY)}d ago`
  return formatGovernDate(value)
}

export function formatGovernStamp(value: string | null | undefined): string {
  const time = toTime(value)
  if (time === null) return "Not recorded"
  const stamp = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(time)
  return `${stamp} UTC`
}

export function formatGovernDate(value: string | null | undefined): string {
  const time = toTime(value)
  if (time === null) return "Not recorded"
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(time)
}

export function formatGovernShortDate(value: string | null | undefined): string {
  const time = toTime(value)
  if (time === null) return "—"
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  }).format(time)
}

export function formatGovernClock(value: string | null | undefined): string {
  const time = toTime(value)
  if (time === null) return "—"
  return `${new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(time)} UTC`
}

export function formatGovernDuration(start: string | null | undefined, end: string | null | undefined): string {
  const from = toTime(start)
  const to = end ? toTime(end) : GOVERN_NOW
  if (from === null || to === null || to < from) return "—"
  const delta = to - from
  if (delta < HOUR) return `${Math.max(1, Math.round(delta / MINUTE))}m`
  if (delta < DAY) return `${Math.max(1, Math.floor(delta / HOUR))}h`
  return `${Math.floor(delta / DAY)}d`
}

export function formatGovernWait(since: string | null | undefined): string {
  const time = toTime(since)
  if (time === null) return "—"
  const delta = Math.max(0, GOVERN_NOW - time)
  if (delta < HOUR) return `${Math.max(1, Math.round(delta / MINUTE))}m`
  if (delta < DAY) return `${Math.round(delta / HOUR)}h`
  return `${Math.floor(delta / DAY)}d`
}

export function formatGovernNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "Not recorded"
  return new Intl.NumberFormat("en-GB").format(value)
}

export function formatGovernPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "Not recorded"
  return `${value.toFixed(digits)}%`
}

export function formatGovernClockSeconds(value: string | null | undefined): string {
  const time = toTime(value)
  if (time === null) return "—"
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(time)
}

export function formatGovernStampSeconds(value: string | null | undefined): string {
  const time = toTime(value)
  if (time === null) return "Not recorded"
  const stamp = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(time)
  return `${stamp} UTC`
}

/** Audit hover format: absolute UTC with milliseconds. */
export function formatGovernStampMillis(value: string | null | undefined): string {
  const time = toTime(value)
  if (time === null) return "Not recorded"
  const stamp = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(time)
  const millis = String(new Date(time).getUTCMilliseconds()).padStart(3, "0")
  return `${stamp}.${millis} UTC`
}

/** Whole-day age, used for baseline certification warnings. */
export function formatGovernAgeDays(value: string | null | undefined): number | null {
  const time = toTime(value)
  if (time === null) return null
  return Math.max(0, Math.floor((GOVERN_NOW - time) / DAY))
}

/** Shortens a `sha256:<hex>` digest for inline display while keeping the full value copyable. */
export function shortDigest(value: string | null | undefined): string {
  if (!value) return "—"
  const [algorithm, digest] = value.includes(":") ? value.split(":", 2) : ["", value]
  if (!digest) return value
  const prefix = algorithm ? `${algorithm}:` : ""
  if (digest.length <= 12) return `${prefix}${digest}`
  return `${prefix}${digest.slice(0, 4)}…${digest.slice(-4)}`
}
