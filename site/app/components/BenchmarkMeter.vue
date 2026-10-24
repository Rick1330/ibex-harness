<script setup lang="ts">
interface MeterItem {
  label: string
  value: number
  display: string
  note?: string
  color?: string
}

const props = withDefaults(defineProps<{
  items: MeterItem[]
  max?: number
  threshold?: { value: number, label: string }
  total?: MeterItem
}>(), {
  max: undefined,
  threshold: undefined,
  total: undefined,
})

const ceiling = computed(() => {
  const values = props.items.map(item => item.value)
  if (props.total) values.push(props.total.value)
  if (props.threshold) values.push(props.threshold.value)
  const largest = Math.max(...values, 0)
  return props.max ?? (largest > 0 ? largest * 1.08 : 1)
})

function width(value: number) {
  return `${Math.min(100, Math.max(0, (value / ceiling.value) * 100))}%`
}

const thresholdLeft = computed(() => (props.threshold ? width(props.threshold.value) : '0%'))
</script>

<template>
  <div>
    <div
      v-for="item in items"
      :key="item.label"
      class="grid grid-cols-[minmax(5.5rem,0.8fr)_minmax(0,1.5fr)_auto] items-center gap-3 border-b border-[var(--site-line)] py-3 first:pt-0 last:border-b-0"
    >
      <div>
        <p class="m-0 font-mono text-[0.68rem] uppercase tracking-[0.1em] text-[var(--site-ink)]">{{ item.label }}</p>
        <p v-if="item.note" class="m-0 mt-0.5 text-[0.68rem] leading-snug text-[var(--site-muted)]">{{ item.note }}</p>
      </div>
      <div class="relative h-2.5 overflow-hidden rounded-full bg-[var(--site-code-bg)]" role="img" :aria-label="`${item.label}: ${item.display}`">
        <div class="h-full rounded-full" :style="{ width: width(item.value), background: item.color ?? 'var(--site-signal)' }" />
        <div
          v-if="props.threshold"
          class="absolute inset-y-0 w-px bg-[var(--site-ink)]"
          :style="{ left: thresholdLeft }"
        />
      </div>
      <span class="site-mono min-w-[4.5rem] text-right text-xs tabular-nums">{{ item.display }}</span>
    </div>

    <div
      v-if="props.threshold"
      class="flex items-center gap-2 border-b border-[var(--site-line)] py-2 font-mono text-[0.6rem] uppercase tracking-[0.1em] text-[var(--site-muted)]"
    >
      <span class="inline-block h-2 w-px bg-[var(--site-ink)]" />
      {{ props.threshold.label }}
    </div>

    <div
      v-if="props.total"
      class="mt-3 grid grid-cols-[minmax(5.5rem,0.8fr)_minmax(0,1.5fr)_auto] items-center gap-3 border-t border-[var(--site-line)] pt-3"
    >
      <p class="m-0 font-mono text-[0.68rem] uppercase tracking-[0.1em]">{{ props.total.label }}</p>
      <div class="h-2.5 overflow-hidden rounded-full bg-[var(--site-code-bg)]">
        <div class="h-full rounded-full bg-[var(--site-ink)]" :style="{ width: width(props.total.value) }" />
      </div>
      <span class="site-mono min-w-[4.5rem] text-right text-xs tabular-nums">{{ props.total.display }}</span>
    </div>
  </div>
</template>
