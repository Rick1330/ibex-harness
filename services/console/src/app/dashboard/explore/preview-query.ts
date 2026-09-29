import type { ExploreTab, QueryChip, TraceListItem } from "@/lib/explore/types"

const QUERY_FIELDS = [
  "agent",
  "session",
  "model",
  "provider",
  "status",
  "error",
  "directive_version",
  "tool",
] as const

function matchesChip(row: TraceListItem, chip: QueryChip): boolean {
  const value = chip.value.toLowerCase()
  switch (chip.field) {
    case "agent":
      return row.agent.toLowerCase().includes(value)
    case "session":
      return row.session_id.toLowerCase().includes(value)
    case "model":
      return row.model.toLowerCase().includes(value)
    case "provider":
      return row.provider.toLowerCase().includes(value)
    case "status":
      return row.status === chip.value
    case "text":
      return (
        row.trace_id.toLowerCase().includes(value) ||
        row.agent.toLowerCase().includes(value)
      )
    default:
      return true
  }
}

export function filterTraces(
  rows: TraceListItem[],
  chips: QueryChip[],
): TraceListItem[] {
  return chips.length
    ? rows.filter((row) => chips.every((chip) => matchesChip(row, chip)))
    : rows
}

export function parseChips(query: string | null): QueryChip[] {
  if (!query) return []
  return query
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => {
      const index = part.indexOf(":")
      if (index > 0) {
        const field = part.slice(0, index)
        return {
          id: `${field}-${part.slice(index + 1)}`,
          field: (QUERY_FIELDS as readonly string[]).includes(field)
            ? (field as QueryChip["field"])
            : "text",
          value: part.slice(index + 1),
        }
      }
      return { id: `text-${part}`, field: "text" as const, value: part }
    })
}

export function parseTab(value: string | null): ExploreTab {
  return value === "traces" || value === "sessions" || value === "failures"
    ? value
    : "traces"
}
