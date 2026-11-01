<script setup lang="ts">
import { computed } from "vue"
import type { DiffSummary } from "@/lib/govern-diff"

const props = withDefaults(
  defineProps<{
    summary: DiffSummary
    from?: string | null
    to?: string | null
    compact?: boolean
  }>(),
  { from: null, to: null, compact: false },
)

const changed = computed(() => props.summary.sectionsChanged > 0)
</script>

<template>
  <div class="flex flex-wrap items-center gap-1.5 text-xs leading-5" :class="compact && 'gap-1'">
    <span v-if="from && to" class="rounded border border-line-subtle bg-surface-2 px-1.5 font-mono text-[0.6875rem] text-fg-2">
      {{ from }} → {{ to }}
    </span>
    <span
      v-if="changed"
      class="rounded-full border border-warn/30 bg-warn-tint px-2 font-medium text-warn"
    >
      {{ summary.sectionsChanged }} of {{ summary.sectionsTotal }} sections changed
    </span>
    <span v-else class="rounded-full border border-line-subtle bg-raised px-2 font-medium text-fg-3">
      No textual changes
    </span>
    <span
      v-if="summary.added > 0"
      class="rounded-full border border-diff-add/30 bg-diff-add-bg px-2 font-mono tabular-nums text-diff-add"
      :aria-label="`${summary.added} lines added`"
    >+{{ summary.added }}</span>
    <span
      v-if="summary.removed > 0"
      class="rounded-full border border-diff-remove/30 bg-diff-remove-bg px-2 font-mono tabular-nums text-diff-remove"
      :aria-label="`${summary.removed} lines removed`"
    >−{{ summary.removed }}</span>
  </div>
</template>
