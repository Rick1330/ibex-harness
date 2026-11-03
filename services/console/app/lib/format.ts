const DASH = "—"

export function formatUtc(value: string | null | undefined): string {
  if (!value) return DASH
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return DASH
  return `${date.toISOString().slice(0, 19).replace("T", " ")} UTC`
}

export function formatCompactUtc(value: string | null | undefined): string {
  if (!value) return DASH
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return DASH
  return `${new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(date)} UTC`
}

export function formatDayTimeUtc(value: string | null | undefined): string {
  if (!value) return DASH
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return DASH
  const parts = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).formatToParts(date)
  const part = (type: Intl.DateTimeFormatPartTypes): string => parts.find((entry) => entry.type === type)?.value ?? ""
  return `${part("day")} ${part("month")} ${part("year")} · ${part("hour")}:${part("minute")}`
}

export function shortenId(value: string | null | undefined, head = 8, tail = 4): string {
  if (!value) return DASH
  if (value.length <= head + tail + 1) return value
  return `${value.slice(0, head)}…${value.slice(-tail)}`
}

export function formatNumber(value: number | null | undefined): string {
  if (value == null) return DASH
  return new Intl.NumberFormat("en-US").format(value)
}

export function formatDuration(value: number | null | undefined): string {
  if (value == null) return DASH
  if (value < 1_000) return `${Math.round(value)} ms`
  return `${(value / 1_000).toFixed(value >= 10_000 ? 1 : 2)} s`
}

export function formatSeconds(value: number | null | undefined): string {
  if (value == null) return DASH
  if (value < 60) return `${value.toFixed(value < 10 ? 1 : 0)} s`
  if (value < 3_600) return `${(value / 60).toFixed(1)} min`
  return `${(value / 3_600).toFixed(1)} h`
}

export function formatNullable(value: string | number | null | undefined): string {
  if (value == null || value === "") return DASH
  return String(value)
}

export function humanize(value: string): string {
  return value.replaceAll("_", " ")
}
