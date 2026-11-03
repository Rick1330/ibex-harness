<script setup lang="ts">
export interface GraphLegendItem {
  label: string
  value: string
  color?: string
}

const props = withDefaults(defineProps<{
  title: string
  meta?: string
  legend?: GraphLegendItem[]
  caption?: string
  expandable?: boolean
}>(), {
  meta: '',
  legend: () => [],
  caption: '',
  expandable: true,
})

const emit = defineEmits<{ expand: [] }>()
</script>

<template>
  <article class="bench-graph-card">
    <header class="flex items-start justify-between gap-4">
      <div class="min-w-0">
        <h3 class="m-0 text-[0.94rem] font-medium tracking-[-0.015em]">{{ props.title }}</h3>
        <p v-if="props.meta" class="m-0 mt-1 font-mono text-[0.54rem] uppercase tracking-[0.1em] text-[var(--site-muted)]">
          {{ props.meta }}
        </p>
      </div>
      <button
        v-if="props.expandable"
        type="button"
        class="grid size-7 shrink-0 place-items-center rounded-md text-[var(--site-muted)] transition-colors hover:bg-[color-mix(in_srgb,var(--site-ink)_6%,transparent)] hover:text-[var(--site-ink)]"
        :aria-label="`Expand ${props.title}`"
        @click="emit('expand')"
      >
        <UIcon name="i-lucide-maximize-2" class="size-3.5" />
      </button>
    </header>

    <div class="bench-graph-card__chart mt-5">
      <slot />
    </div>

    <div v-if="props.legend.length" class="mt-5 grid gap-2.5 pt-1">
      <div v-for="item in props.legend" :key="item.label" class="flex items-center gap-2.5 text-[0.7rem]">
        <span class="size-1.5 shrink-0 rounded-full" :style="{ background: item.color ?? 'var(--chart-lime)' }" />
        <span class="text-[var(--site-muted)]">{{ item.label }}</span>
        <span class="ml-auto font-mono tabular-nums text-[var(--site-ink)]">{{ item.value }}</span>
      </div>
    </div>

    <p v-if="props.caption" class="m-0 mt-4 border-t border-[var(--site-line)] pt-3 text-[0.66rem] leading-relaxed text-[var(--site-muted)]">
      {{ props.caption }}
    </p>
  </article>
</template>
