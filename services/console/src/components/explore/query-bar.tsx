"use client"

import { insetClass } from "@/components/sessions/dashboard-shell"
import * as React from "react"
import { IconStar, IconX } from "@tabler/icons-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { QUERY_SUGGESTIONS } from "@/lib/explore/fixtures"
import type { QueryChip, QueryField } from "@/lib/explore/types"
import { cn } from "@/lib/utils"

const PREFIXES: { field: Exclude<QueryField, "text">; prefix: string }[] = [
  { field: "agent", prefix: "agent:" },
  { field: "session", prefix: "session:" },
  { field: "model", prefix: "model:" },
  { field: "provider", prefix: "provider:" },
  { field: "status", prefix: "status:" },
  { field: "error", prefix: "error:" },
  { field: "directive_version", prefix: "directive_version:" },
  { field: "tool", prefix: "tool:" },
]

/** Query chips only — time range lives in the site header. */
export function ExploreQueryBar({
  chips,
  onChipsChange,
  onSaveView,
}: {
  chips: QueryChip[]
  onChipsChange: (chips: QueryChip[]) => void
  onSaveView: () => void
}) {
  const [draft, setDraft] = React.useState("")
  const [open, setOpen] = React.useState(false)
  const inputRef = React.useRef<HTMLInputElement>(null)

  const suggestions = React.useMemo(() => {
    const lower = draft.trim().toLowerCase()
    if (!lower) {
      return PREFIXES.map((p) => ({
        kind: "prefix" as const,
        label: p.prefix,
        field: p.field,
        value: "",
      }))
    }

    const matchedPrefix = PREFIXES.find(
      (p) => lower.startsWith(p.prefix) || p.prefix.startsWith(lower),
    )

    if (matchedPrefix) {
      const after = lower.startsWith(matchedPrefix.prefix)
        ? draft.slice(matchedPrefix.prefix.length)
        : ""
      const values = QUERY_SUGGESTIONS[matchedPrefix.field] ?? []
      return values
        .filter((v) =>
          after ? v.toLowerCase().includes(after.toLowerCase()) : true,
        )
        .slice(0, 8)
        .map((v) => ({
          kind: "value" as const,
          label: `${matchedPrefix.prefix}${v}`,
          field: matchedPrefix.field,
          value: v,
        }))
    }

    return PREFIXES.filter((p) => p.prefix.includes(lower)).map((p) => ({
      kind: "prefix" as const,
      label: p.prefix,
      field: p.field,
      value: "",
    }))
  }, [draft])

  const addChip = (field: QueryField, value: string) => {
    if (!value.trim() && field !== "text") return
    const next: QueryChip = {
      id: `${field}-${value}-${crypto.randomUUID().slice(0, 6)}`,
      field,
      value: value.trim(),
    }
    onChipsChange([...chips, next])
    setDraft("")
    setOpen(false)
    inputRef.current?.focus()
  }

  const commitDraft = () => {
    const raw = draft.trim()
    if (!raw) return
    const matched = PREFIXES.find((p) => raw.toLowerCase().startsWith(p.prefix))
    if (matched) {
      const value = raw.slice(matched.prefix.length).trim()
      if (value) addChip(matched.field, value)
      return
    }
    addChip("text", raw)
  }

  const removeChip = (id: string) => {
    onChipsChange(chips.filter((c) => c.id !== id))
  }

  return (
    <div
      className={`flex flex-wrap items-center gap-2 ${insetClass} px-3 py-2`}
    >
      <div className="relative min-w-0 flex-1">
        <div
          className={cn(
            "flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border border-input bg-background px-2 py-1",
            "focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/50",
          )}
          role="button"
          tabIndex={0}
          onClick={() => inputRef.current?.focus()}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault()
              inputRef.current?.focus()
            }
          }}
        >
          {chips.map((chip) => (
            <span
              key={chip.id}
              className="inline-flex max-w-full items-center gap-1 rounded-full border bg-muted/60 px-2 py-0.5 font-mono text-[13px]"
            >
              <span className="truncate text-muted-foreground">
                {chip.field === "text" ? "" : `${chip.field}:`}
              </span>
              <span className="truncate">{chip.value}</span>
              <button
                type="button"
                className="rounded-full p-0.5 hover:bg-background"
                onClick={() => removeChip(chip.id)}
                aria-label={`Remove ${chip.field} filter`}
              >
                <IconX className="size-3.5" />
              </button>
            </span>
          ))}
          <Input
            ref={inputRef}
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value)
              setOpen(true)
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => window.setTimeout(() => setOpen(false), 150)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault()
                if (suggestions[0]?.kind === "value" && suggestions[0].value) {
                  addChip(suggestions[0].field, suggestions[0].value)
                } else {
                  commitDraft()
                }
              }
              if (e.key === "Backspace" && !draft && chips.length) {
                removeChip(chips[chips.length - 1].id)
              }
              if (e.key === "Escape") setOpen(false)
            }}
            placeholder={
              chips.length
                ? "Add filter…"
                : "agent: · session: · model: · status: · free text"
            }
            className="h-7 min-w-[12rem] flex-1 border-0 bg-transparent px-1 text-[13px] shadow-none focus-visible:ring-0"
            aria-label="Explore query"
            aria-autocomplete="list"
            aria-expanded={open}
          />
        </div>
        {open && suggestions.length > 0 && (
          <ul
            className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-md border bg-popover p-1 shadow-md"
            role="listbox"
          >
            {suggestions.map((s) => (
              <li key={s.label}>
                <button
                  type="button"
                  role="option"
                  className="flex w-full rounded-sm px-2 py-1.5 text-left font-mono text-[13px] hover:bg-muted"
                  aria-selected={false}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => {
                    if (s.kind === "prefix") {
                      setDraft(s.label)
                      inputRef.current?.focus()
                    } else {
                      addChip(s.field, s.value)
                    }
                  }}
                >
                  {s.label}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Button
        type="button"
        size="sm"
        variant="outline"
        className="h-8"
        onClick={onSaveView}
        title="Saved views are URLs — pinned to sidebar, not server objects"
      >
        <IconStar className="size-3.5" />
        Save view
      </Button>
    </div>
  )
}
