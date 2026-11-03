<script setup lang="ts">
import { computed, ref, watch } from "vue"
import type { AuditRedaction } from "@/lib/audit-preview"

type DiffMode = "summary" | "changed" | "full"

const props = withDefaults(
  defineProps<{
    before: Record<string, unknown> | null
    after: Record<string, unknown> | null
    summaries?: string[]
    redactions?: AuditRedaction[]
    defaultMode?: DiffMode
  }>(),
  { summaries: () => [], redactions: () => [], defaultMode: "changed" },
)

interface Entry {
  path: string
  before: unknown
  after: unknown
  hasBefore: boolean
  hasAfter: boolean
  changed: boolean
}

const MODES: { id: DiffMode; label: string }[] = [
  { id: "summary", label: "Summary" },
  { id: "changed", label: "Changed keys" },
  { id: "full", label: "Full JSON" },
]

const mode = ref<DiffMode>(props.defaultMode)
watch(
  () => [props.before, props.after],
  () => {
    mode.value = props.defaultMode
  },
)

const entries = computed<Entry[]>(() => {
  const beforeMap = new Map<string, unknown>()
  const afterMap = new Map<string, unknown>()
  flatten(props.before, "", beforeMap)
  flatten(props.after, "", afterMap)
  const keys = [...new Set([...beforeMap.keys(), ...afterMap.keys()])].sort((left, right) => left.localeCompare(right))
  return keys.map((path) => {
    const hasBefore = beforeMap.has(path)
    const hasAfter = afterMap.has(path)
    const before = beforeMap.get(path)
    const after = afterMap.get(path)
    return {
      path,
      before,
      after,
      hasBefore,
      hasAfter,
      changed: hasBefore !== hasAfter || JSON.stringify(before) !== JSON.stringify(after),
    }
  })
})

function flatten(value: unknown, prefix: string, map: Map<string, unknown>): void {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const record = value as Record<string, unknown>
    const keys = Object.keys(record)
    if (keys.length === 0) {
      map.set(prefix || "value", {})
      return
    }
    for (const key of keys) flatten(record[key], prefix ? `${prefix}.${key}` : key, map)
    return
  }
  map.set(prefix || "value", value)
}

const changedEntries = computed(() => entries.value.filter((entry) => entry.changed))

const generatedSummaries = computed(() =>
  changedEntries.value.map((entry) => {
    const label = entry.path.replaceAll(".", " › ")
    if (!entry.hasBefore) return `${label} was added.`
    if (!entry.hasAfter) return `${label} was removed.`
    return `${label} changed from ${inline(entry.before)} to ${inline(entry.after)}.`
  }),
)

const summaryLines = computed(() => (props.summaries.length ? props.summaries : generatedSummaries.value))

function inline(value: unknown): string {
  if (value === null) return "null"
  if (typeof value === "string") return value
  return JSON.stringify(value) ?? String(value)
}

function display(value: unknown, has: boolean): string {
  if (!has) return "—"
  return inline(value)
}

const redactionRules = computed(() => new Map(props.redactions.map((entry) => [entry.field, entry.ruleId])))

function isRedacted(value: unknown): boolean {
  return value === "[redacted]"
}

function redactionRule(path: string): string | null {
  for (const [field, rule] of redactionRules.value.entries()) {
    if (path === field || path.endsWith(`.${field}`)) return rule ?? "redaction rule not recorded"
  }
  return redactionRules.value.get(path) ?? null
}

type FullRow = { kind: "row"; entry: Entry } | { kind: "skip"; count: number }

const fullRows = computed<FullRow[]>(() => {
  const rows: FullRow[] = []
  const hasChanges = changedEntries.value.length > 0
  let run = 0
  for (const entry of entries.value) {
    if (hasChanges && !entry.changed) {
      run += 1
      continue
    }
    if (run > 0) {
      rows.push({ kind: "skip", count: run })
      run = 0
    }
    rows.push({ kind: "row", entry })
  }
  if (run > 0) rows.push({ kind: "skip", count: run })
  return rows
})
</script>

<template>
  <div class="min-w-0">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="flex rounded-md border border-line-subtle bg-surface-1 p-0.5" role="tablist" aria-label="Diff view">
        <button
          v-for="option in MODES"
          :key="option.id"
          type="button"
          role="tab"
          :aria-selected="mode === option.id"
          class="h-7 rounded px-2 text-[0.6875rem] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
          :class="mode === option.id ? 'bg-raised text-fg-1' : 'text-fg-3 hover:text-fg-1'"
          @click="mode = option.id"
        >
          {{ option.label }}
        </button>
      </div>
      <span class="text-[0.6875rem] text-fg-3">
        {{ changedEntries.length }} changed {{ changedEntries.length === 1 ? "key" : "keys" }}
      </span>
    </div>

    <div v-if="mode === 'summary'" class="mt-2 rounded-lg border border-line-subtle bg-surface-2/60 px-3 py-2.5">
      <ul v-if="summaryLines.length" class="space-y-1 text-xs leading-5 text-fg-2">
        <li v-for="line in summaryLines" :key="line" class="flex items-start gap-1.5">
          <span class="mt-1.5 size-1 shrink-0 rounded-full bg-fg-3" aria-hidden="true" />
          <span>{{ line }}</span>
        </li>
      </ul>
      <p v-else class="text-xs text-fg-3">No changed keys in this record.</p>
    </div>

    <div v-else-if="mode === 'changed'" class="mt-2 overflow-hidden rounded-lg border border-line-subtle">
      <table v-if="changedEntries.length" class="ix-agent-table" aria-label="Changed keys">
        <thead>
          <tr>
            <th scope="col" class="w-48">Key</th>
            <th scope="col">Before</th>
            <th scope="col">After</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in changedEntries" :key="entry.path">
            <td class="font-mono text-[0.6875rem] text-fg-2">{{ entry.path }}</td>
            <td class="font-mono text-[0.6875rem] break-all text-fg-3">
              <span
                v-if="isRedacted(entry.before)"
                class="inline-flex items-center rounded border border-line bg-raised px-1.5 py-0.5 text-[0.625rem] text-fg-3"
                :title="redactionRule(entry.path) ?? 'Redacted'"
              >[redacted]</span>
              <template v-else>{{ display(entry.before, entry.hasBefore) }}</template>
            </td>
            <td class="font-mono text-[0.6875rem] break-all text-fg-1">
              <span
                v-if="isRedacted(entry.after)"
                class="inline-flex items-center rounded border border-line bg-raised px-1.5 py-0.5 text-[0.625rem] text-fg-3"
                :title="redactionRule(entry.path) ?? 'Redacted'"
              >[redacted]</span>
              <template v-else>{{ display(entry.after, entry.hasAfter) }}</template>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="px-3 py-4 text-xs text-fg-3">No changed keys in this record.</p>
    </div>

    <div v-else class="mt-2 overflow-hidden rounded-lg border border-line-subtle">
      <template v-for="(row, index) in fullRows" :key="row.kind === 'row' ? row.entry.path : `skip-${index}`">
        <p v-if="row.kind === 'skip'" class="border-b border-line-subtle bg-surface-2/40 px-3 py-1 font-mono text-[0.625rem] text-fg-3">
          … {{ row.count }} unchanged {{ row.count === 1 ? "line" : "lines" }}
        </p>
        <div
          v-else
          class="grid grid-cols-1 gap-1 border-b border-line-subtle px-3 py-1.5 last:border-0 sm:grid-cols-[minmax(0,11rem)_minmax(0,1fr)_minmax(0,1fr)] sm:gap-3"
        >
          <span class="font-mono text-[0.6875rem] break-all text-fg-2">{{ row.entry.path }}</span>
          <span class="font-mono text-[0.6875rem] break-all" :class="row.entry.changed ? 'text-fg-3 line-through decoration-crit/40' : 'text-fg-3'">
            {{ display(row.entry.before, row.entry.hasBefore) }}
          </span>
          <span class="font-mono text-[0.6875rem] break-all" :class="row.entry.changed ? 'text-fg-1' : 'text-fg-3'">
            {{ display(row.entry.after, row.entry.hasAfter) }}
          </span>
        </div>
      </template>
      <p v-if="entries.length === 0" class="px-3 py-4 text-xs text-fg-3">No JSON recorded for this record.</p>
    </div>
  </div>
</template>
