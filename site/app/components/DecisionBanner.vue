<script setup lang="ts">
const props = withDefaults(defineProps<{
  status?: string
  date?: string
  id?: string
}>(), {
  status: 'Proposed',
  date: '',
  id: '',
})

const normalized = computed(() => props.status.toLowerCase())
const tone = computed(() => {
  if (normalized.value === 'accepted') return 'border-l-[var(--site-signal)]'
  if (normalized.value === 'rejected') return 'border-l-[#d64545]'
  if (normalized.value === 'superseded') return 'border-l-[var(--color-amber)]'
  return 'border-l-[var(--color-ice)]'
})
</script>

<template>
  <div class="my-6 border border-l-2 border-[var(--site-line)] bg-[var(--site-surface)] px-4 py-3" :class="tone">
    <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
      <span class="site-mono text-[0.65rem] font-semibold uppercase tracking-[0.14em] text-[var(--site-muted)]">
        Decision record
      </span>
      <span class="site-mono text-[0.65rem] uppercase tracking-[0.12em]">{{ status }}</span>
      <span v-if="date" class="site-mono text-[0.65rem] text-[var(--site-muted)]">{{ date }}</span>
      <span v-if="id" class="site-mono text-[0.65rem] text-[var(--site-muted)]">ADR-{{ id }}</span>
    </div>
    <p class="m-0 mt-1.5 text-xs leading-relaxed text-[var(--site-muted)]">
      A decision record explains a choice. It is not, by itself, evidence that the runtime is implemented or accepted.
    </p>
  </div>
</template>
