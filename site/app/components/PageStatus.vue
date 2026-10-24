<script setup lang="ts">
import { statusMeta, type Status } from '~/data/ledger'

const props = withDefaults(defineProps<{
  status?: string
  verified?: string
  source?: string
  note?: string
}>(), {
  status: 'UNKNOWN',
  verified: '',
  source: '',
  note: '',
})

const normalized = computed<Status>(() => {
  const value = String(props.status || 'UNKNOWN').toUpperCase()
  return (value in statusMeta ? value : 'UNKNOWN') as Status
})

const meta = computed(() => statusMeta[normalized.value])
</script>

<template>
  <div class="my-6 flex flex-col gap-3 border border-[var(--site-line)] bg-[var(--site-surface)] px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
    <div class="flex flex-wrap items-center gap-3">
      <StatusBadge :status="normalized" />
      <span class="site-mono text-[0.66rem] uppercase tracking-[0.12em] text-[var(--site-muted)]">
        Ledger class: {{ meta.ledgerClass }}
      </span>
    </div>
    <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--site-muted)]">
      <span v-if="verified">Verified {{ verified }}</span>
      <span v-if="note">{{ note }}</span>
      <NuxtLink v-if="source" to="/docs/architecture/status-and-evidence" class="site-link">
        Evidence ledger
      </NuxtLink>
    </div>
  </div>
</template>
