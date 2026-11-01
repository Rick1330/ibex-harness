<script setup lang="ts">
import MemoryEmptyValue from "@/components/console/memory/primitives/MemoryEmptyValue.vue"

export type KeyValueRow = {
  label: string
  value?: string | number | null
  mono?: boolean
  tone?: "default" | "muted" | "success" | "warning" | "destructive"
}

withDefaults(
  defineProps<{
    rows: KeyValueRow[]
    /** Set false when the caller renders a paragraph under the list instead of a value column. */
    dividers?: boolean
  }>(),
  { dividers: true },
)

function toneClass(tone: KeyValueRow["tone"]): string {
  if (tone === "success") return "text-ok"
  if (tone === "warning") return "text-warn"
  if (tone === "destructive") return "text-crit"
  if (tone === "muted") return "text-fg-3"
  return "text-fg-1"
}
</script>

<template>
  <dl class="min-w-0">
    <div
      v-for="row in rows"
      :key="row.label"
      class="grid min-h-9 grid-cols-[7rem_minmax(0,1fr)] items-baseline gap-3 py-1.5"
      :class="dividers && 'border-b border-line-subtle last:border-b-0'"
    >
      <dt class="text-[0.8125rem] leading-5 text-fg-3">{{ row.label }}</dt>
      <dd class="min-w-0 text-[0.8125rem] leading-5" :class="toneClass(row.tone)">
        <slot name="value" :row="row">
          <MemoryEmptyValue v-if="row.value === null || row.value === undefined || row.value === ''" />
          <span v-else :class="row.mono && 'font-mono text-xs tabular-nums'">{{ row.value }}</span>
        </slot>
      </dd>
    </div>
  </dl>
</template>
