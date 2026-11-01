<script setup lang="ts">
import { computed } from "vue"
import { formatDayTimeUtc } from "@/lib/format"
import {
  MEMORY_SOURCE_LABELS,
  MEMORY_VISIBILITY_LABELS,
  memoryRelativeTime,
} from "@/lib/memory-preview"
import type { MemoryDetail } from "@/lib/memory-detail-preview"
import MemoryStatusPill from "./primitives/MemoryStatusPill.vue"
import MemoryEmptyValue from "./primitives/MemoryEmptyValue.vue"
import MemoryScoreBar from "./primitives/MemoryScoreBar.vue"
import MemoryCompleteness from "./primitives/MemoryCompleteness.vue"

const props = defineProps<{ detail: MemoryDetail }>()

const memory = computed(() => props.detail.memory)
const agentInitials = computed(() =>
  memory.value.agent
    .split(/\s+/)
    .map((word) => word[0])
    .join("")
    .slice(0, 2)
    .toUpperCase(),
)

type Row = {
  label: string
  value?: string | null
  mono?: boolean
  relative?: boolean
  slot?: "status" | "agent" | "creator"
  hint?: string
}

const scopeRows = computed<Row[]>(() => [
  { label: "Subject", value: props.detail.subject },
  { label: "Applies to", value: props.detail.appliesTo.length ? props.detail.appliesTo.join(" · ") : null },
  { label: "Eligible agent", slot: "agent" },
  { label: "Visibility", value: MEMORY_VISIBILITY_LABELS[memory.value.visibility] },
  { label: "Created by", slot: "creator" },
])

const lifecycleRows = computed<Row[]>(() => [
  { label: "Status", slot: "status" },
  { label: "Effective from", value: formatDayTimeUtc(memory.value.validFrom), mono: true },
  { label: "Expires", value: memory.value.validUntil ? formatDayTimeUtc(memory.value.validUntil) : null, mono: true },
  { label: "Last verified", value: props.detail.lastVerifiedAt ? formatDayTimeUtc(props.detail.lastVerifiedAt) : null, mono: true },
  { label: "Revision", value: `r${props.detail.lifecycleRevision}`, mono: true },
  {
    label: "Review",
    value:
      memory.value.conflict?.state === "open"
        ? "Contradiction open"
        : memory.value.status === "quarantined"
          ? "Human review required"
          : ["archived", "superseded", "merged_into", "deleted"].includes(memory.value.status)
            ? "Retired record"
            : null,
    hint:
      memory.value.status === "active"
        ? "An unexpired record is not automatically a recently verified record."
        : undefined,
  },
])

const provenanceRows = computed<Row[]>(() => [
  { label: "Source", value: MEMORY_SOURCE_LABELS[memory.value.source] },
  { label: "Session", value: memory.value.sessionId, mono: true },
  {
    label: "Method",
    value: memory.value.source === "user_provided" ? "User-provided statement" : null,
  },
])
</script>

<template>
  <div class="flex min-w-0 flex-col gap-4">
    <section aria-labelledby="memory-rail-scope" class="rounded-lg border border-line-subtle bg-surface p-4">
      <h2 id="memory-rail-scope" class="text-sm leading-5 font-semibold text-fg-1">Scope</h2>
      <dl class="mt-1 divide-y divide-line-subtle">
        <div v-for="row in scopeRows" :key="row.label" class="grid grid-cols-[6.5rem_minmax(0,1fr)] items-baseline gap-2 py-2">
          <dt class="text-xs leading-5 text-fg-3">{{ row.label }}</dt>
          <dd class="min-w-0 text-[0.8125rem] leading-5 text-fg-1">
            <MemoryEmptyValue v-if="row.slot !== 'agent' && row.slot !== 'creator' && !row.value" />
            <NuxtLink
              v-else-if="row.slot === 'agent'"
              :to="`/agents?agent=${encodeURIComponent(memory.agentId)}`"
              class="inline-flex items-center gap-1.5 rounded transition-colors hover:text-accent"
            >
              <span class="ix-avatar ix-avatar-sm" aria-hidden="true">{{ agentInitials }}</span>
              <span class="truncate underline decoration-line-strong underline-offset-3">{{ memory.agent }}</span>
            </NuxtLink>
            <span v-else-if="row.slot === 'creator'" class="group/copy inline-flex min-w-0 items-center gap-1.5">
              <template v-if="detail.createdByUser">
                <span class="font-mono text-xs text-fg-2 group-hover/copy:text-fg-1">{{ detail.createdByUser }}</span>
              </template>
              <template v-else>
                <span class="truncate">{{ memory.agent }}</span>
                <span class="font-mono text-xs text-fg-3">{{ memory.agentId }}</span>
              </template>
            </span>
            <span v-else>{{ row.value }}</span>
          </dd>
        </div>
      </dl>
    </section>

    <section aria-labelledby="memory-rail-lifecycle" class="rounded-lg border border-line-subtle bg-surface p-4">
      <h2 id="memory-rail-lifecycle" class="text-sm leading-5 font-semibold text-fg-1">Lifecycle</h2>
      <dl class="mt-1 divide-y divide-line-subtle">
        <div v-for="row in lifecycleRows" :key="row.label" class="grid grid-cols-[6.5rem_minmax(0,1fr)] items-baseline gap-2 py-2">
          <dt class="text-xs leading-5 text-fg-3">{{ row.label }}</dt>
          <dd class="min-w-0 text-[0.8125rem] leading-5 text-fg-1">
            <MemoryStatusPill v-if="row.slot === 'status'" :status="memory.status" />
            <MemoryEmptyValue v-else-if="!row.value" />
            <span v-else :class="row.mono && 'font-mono text-xs tabular-nums'">{{ row.value }}</span>
            <span v-if="row.hint" class="mt-0.5 block text-xs leading-4 font-normal text-fg-3">{{ row.hint }}</span>
          </dd>
        </div>
      </dl>
    </section>

    <section aria-labelledby="memory-rail-provenance" class="rounded-lg border border-line-subtle bg-surface p-4">
      <h2 id="memory-rail-provenance" class="text-sm leading-5 font-semibold text-fg-1">Provenance</h2>
      <dl class="mt-1 divide-y divide-line-subtle">
        <div v-for="row in provenanceRows" :key="row.label" class="grid grid-cols-[6.5rem_minmax(0,1fr)] items-baseline gap-2 py-2">
          <dt class="text-xs leading-5 text-fg-3">{{ row.label }}</dt>
          <dd class="min-w-0 text-[0.8125rem] leading-5 text-fg-1">
            <MemoryEmptyValue v-if="!row.value" />
            <NuxtLink
              v-else-if="row.label === 'Session' && memory.sessionId"
              :to="`/sessions/${encodeURIComponent(memory.sessionId)}`"
              class="font-mono text-xs underline decoration-line-strong underline-offset-3 hover:text-accent hover:decoration-accent"
            >
              {{ row.value }}
            </NuxtLink>
            <span v-else>{{ row.value }}</span>
          </dd>
        </div>
      </dl>
      <div class="mt-3 border-t border-line-subtle pt-3">
        <div class="flex items-baseline justify-between gap-2">
          <span class="text-xs leading-4 text-fg-3">Confidence</span>
          <span class="font-mono text-xs font-semibold text-fg-1 tabular-nums">{{ memory.confidence.toFixed(2) }}</span>
        </div>
        <div class="mt-1.5">
          <MemoryScoreBar :value="memory.confidence" label="Extraction confidence" />
        </div>
        <p class="mt-1.5 text-[0.6875rem] leading-3.5 text-fg-3">Confidence updated {{ memoryRelativeTime(memory.updatedAt) }}.</p>
      </div>
    </section>

    <MemoryCompleteness :detail="detail" />
  </div>
</template>
