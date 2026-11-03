<script setup lang="ts">
import { statusMeta, type Status } from '~/data/ledger'

const props = withDefaults(defineProps<{
  status?: string
  label?: string
}>(), {
  status: 'UNKNOWN',
  label: '',
})

const normalized = computed<Status>(() => {
  const value = String(props.status || 'UNKNOWN').toUpperCase()
  return (value in statusMeta ? value : 'UNKNOWN') as Status
})

const meta = computed(() => statusMeta[normalized.value])
</script>

<template>
  <span
    class="site-status"
    :class="`status-${normalized.toLowerCase()}`"
    :title="meta.description"
  >
    {{ label || meta.label }}
  </span>
</template>
