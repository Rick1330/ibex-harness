<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue"
import { Download, Lock } from "@lucide/vue"
import { useAgentTabQueryString } from "@/composables/useAgentTabQuery"
import { agentDayKey, formatAgentDayHeading, formatAgentRelative, formatAgentStamp } from "@/lib/agent-detail"
import type { AgentDetail, AgentAuditEvent } from "@/lib/agent-preview"

const props = defineProps<{ agent: AgentDetail }>()

const TYPE_OPTIONS = ["status", "config", "directive", "policy", "budget", "tags", "memory", "deploy"] as const

const typeFilter = useAgentTabQueryString("atype")
const expanded = ref<string | null>(null)

const filtered = computed(() =>
  typeFilter.value ? props.agent.auditData.filter((event) => event.type === typeFilter.value) : props.agent.auditData,
)

const byDay = computed(() => {
  const days = new Map<string, AgentAuditEvent[]>()
  for (const event of filtered.value) {
    const key = agentDayKey(event.at)
    const list = days.get(key) ?? []
    list.push(event)
    days.set(key, list)
  }
  return [...days.entries()]
})

const destructiveTypes = new Set(["deploy", "status"])

function actorInitials(event: AgentAuditEvent): string {
  return event.initials || event.actor.slice(0, 2).toUpperCase()
}

function exportCsv(): void {
  if (!import.meta.client) return
  const header = ["at", "actor", "type", "operation", "summary", "reason", "before", "after"]
  const cell = (value: unknown): string => {
    const text = value === null || value === undefined ? "" : String(value)
    return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
  }
  const rows = filtered.value.map((event) =>
    [event.at, event.actor, event.type, event.operation, event.summary, event.reason, event.before, event.after]
      .map(cell)
      .join(","),
  )
  const blob = new Blob([[header.join(","), ...rows].join("\n")], { type: "text/csv;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = `ibex-agent-${props.agent.id}-audit.csv`
  link.click()
  URL.revokeObjectURL(url)
}

const copiedExport = ref(false)
let exportTimer: ReturnType<typeof setTimeout> | null = null
function onExport(): void {
  exportCsv()
  copiedExport.value = true
  if (exportTimer) clearTimeout(exportTimer)
  exportTimer = setTimeout(() => {
    copiedExport.value = false
  }, 1_500)
}
onBeforeUnmount(() => {
  if (exportTimer) clearTimeout(exportTimer)
})
</script>

<template>
  <div class="min-w-0 space-y-5">
    <div class="flex flex-wrap items-center gap-2">
      <select v-model="typeFilter" aria-label="Filter audit history by type" class="ix-input h-8 w-auto text-xs">
        <option value="">All types</option>
        <option v-for="option in TYPE_OPTIONS" :key="option" :value="option" class="capitalize">{{ option }}</option>
      </select>
      <span class="text-xs text-fg-3">{{ filtered.length }} events</span>
      <button
        type="button"
        class="ix-button-secondary ml-auto h-8 gap-1.5 px-2.5 text-xs"
        @click="onExport"
      >
        <Download :size="13" :stroke-width="1.9" aria-hidden="true" />
        {{ copiedExport ? "Copied to downloads" : "Export CSV" }}
      </button>
    </div>

    <section aria-labelledby="audit-timeline" class="rounded-lg border border-line-subtle bg-surface-1">
      <h2 id="audit-timeline" class="sr-only">Audit timeline</h2>
      <div v-for="[day, events] in byDay" :key="day" class="border-b border-line-subtle last:border-0">
        <p class="bg-canvas px-5 py-1.5 text-[0.6875rem] font-medium tracking-[0.06em] text-fg-3 uppercase">
          {{ formatAgentDayHeading(events[0]!.at) }}
        </p>
        <ol class="px-5 py-2">
          <li v-for="event in events" :key="event.id" class="relative border-l border-line-subtle pb-4 pl-4 last:pb-0">
            <span
              class="absolute top-1.5 -left-[0.3125rem] size-2.5 rounded-full border-2 bg-surface-1"
              :class="destructiveTypes.has(event.type) ? 'border-crit' : 'border-line-strong'"
              aria-hidden="true"
            />
            <div class="flex flex-wrap items-center gap-x-2.5 gap-y-1">
              <span class="ix-avatar ix-avatar-sm shrink-0" aria-hidden="true">{{ actorInitials(event) }}</span>
              <span class="text-xs font-medium text-fg-2">{{ event.actor }}</span>
              <span
                class="inline-flex h-4.5 items-center rounded px-1.5 font-mono text-[0.625rem] leading-none font-semibold tracking-[0.06em]"
                :class="destructiveTypes.has(event.type) ? 'bg-crit-tint text-crit' : 'bg-raised text-fg-2'"
              >
                {{ event.operation }}
              </span>
              <span class="min-w-0 flex-1 truncate text-xs text-fg-1">{{ event.summary }}</span>
              <span class="shrink-0 font-mono text-xs text-fg-3 tabular-nums" :title="formatAgentStamp(event.at)">
                {{ formatAgentRelative(event.at) }}
              </span>
              <button
                v-if="event.before !== null || event.after !== null"
                type="button"
                class="shrink-0 text-[0.6875rem] text-fg-3 underline decoration-line-strong underline-offset-3 hover:text-fg-1"
                @click="expanded = expanded === event.id ? null : event.id"
              >
                {{ expanded === event.id ? "Hide change" : "Show change" }}
              </button>
            </div>
            <p v-if="event.reason" class="mt-0.5 pl-7 text-xs leading-4 text-fg-3">{{ event.reason }}</p>
            <div v-if="expanded === event.id" class="mt-1.5 ml-7 grid gap-1.5 max-w-xl sm:grid-cols-2">
              <p class="rounded-md border-l-2 border-crit/50 bg-crit-tint/50 px-2.5 py-1.5 font-mono text-[0.6875rem] leading-4 break-words text-fg-3 line-through">
                − {{ event.before ?? "—" }}
              </p>
              <p class="rounded-md border-l-2 border-ok/50 bg-ok-tint/50 px-2.5 py-1.5 font-mono text-[0.6875rem] leading-4 break-words text-fg-1">
                + {{ event.after ?? "—" }}
              </p>
            </div>
          </li>
        </ol>
      </div>
      <p v-if="!filtered.length" class="p-5 text-xs text-fg-3">No audit events match this filter.</p>
    </section>

    <p class="flex items-center gap-1.5 text-xs leading-4 text-fg-3">
      <Lock :size="11" :stroke-width="1.9" aria-hidden="true" />
      Immutable record. The audit trail is append-only and never editable.
    </p>
  </div>
</template>
