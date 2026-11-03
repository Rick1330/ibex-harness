<script setup lang="ts">
import { computed } from "vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernSeverityChip from "@/components/console/govern/primitives/GovernSeverityChip.vue"
import { GOVERN_SEVERITY_LABELS, type GovernSeverity } from "@/lib/govern-severity"
import { formatGovernNumber } from "@/lib/govern-format"
import type { OverviewAttentionRow } from "@/lib/overview-view"

const props = defineProps<{
  rows: OverviewAttentionRow[]
  /** False only while every source is still being read, so the empty card does not lie. */
  settled: boolean
  snapshotLabel: string
}>()

const emit = defineEmits<{ open: [href: string] }>()

const counts = computed(() => {
  const bySeverity: Record<GovernSeverity, number> = { critical: 0, warning: 0, info: 0 }
  for (const row of props.rows) bySeverity[row.severity] += 1
  return bySeverity
})
</script>

<template>
  <section class="flex min-w-0 flex-col gap-2.5" aria-label="Findings on this snapshot">
    <div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5">
      <h2 class="text-sm leading-5 font-medium text-fg-1">
        Findings derived from the values this snapshot reported
      </h2>
      <p class="flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.6875rem] text-fg-3">
        <span v-for="severity in (['critical', 'warning', 'info'] as const)" :key="severity">
          <span class="font-mono tabular-nums text-fg-2">{{ formatGovernNumber(counts[severity]) }}</span>
          {{ GOVERN_SEVERITY_LABELS[severity].toLowerCase() }}
        </span>
      </p>
    </div>

    <p class="text-[0.6875rem] leading-4 text-fg-3">{{ props.snapshotLabel }}</p>

    <div
      v-if="!props.rows.length"
      class="rounded-lg border border-line-subtle bg-surface px-3.5 py-3"
    >
      <GovernEmptyState
        v-if="props.settled"
        title="Nothing is reporting a problem in this snapshot"
        reason="Every dependency check returned ok, degraded mode is off, the dead-letter queue is empty, and the run rows on this page have intact evidence. That is one observation at one time, not a certified all-clear."
        next-step="Incidents, SLO history and evidence coverage are separate contracts and are not read by this page."
        action-label="Read the dependency ledger"
        @action="emit('open', '/platform')"
      />
      <p v-else class="text-xs text-fg-3">Reading every source before any finding is stated.</p>
    </div>

    <ul v-else class="divide-y divide-line-subtle rounded-lg border border-line-subtle bg-surface">
      <li v-for="row in props.rows" :key="row.id" class="flex items-start gap-3 px-3.5 py-3">
        <GovernSeverityChip :severity="row.severity" />
        <div class="min-w-0 flex-1">
          <p class="text-xs leading-5 font-medium text-fg-1">{{ row.title }}</p>
          <p class="mt-0.5 text-[0.8125rem] leading-4 text-fg-3 text-pretty">{{ row.detail }}</p>
          <p class="mt-1 font-mono text-[0.625rem] leading-4 text-fg-3" :title="`Reported by ${row.origin}`">
            {{ row.origin }}
          </p>
        </div>
        <button
          v-if="row.link"
          type="button"
          class="ix-button-secondary h-7 shrink-0 gap-1 px-2 text-xs"
          @click="emit('open', row.link.href)"
        >
          {{ row.link.label }}
        </button>
      </li>
    </ul>
  </section>
</template>
