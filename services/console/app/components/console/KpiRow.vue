<script setup lang="ts">
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"

type KpiItem = {
  label: string
  value: string
  helper?: string | null
  tone?: "default" | "warning" | "critical" | "success"
}

withDefaults(
  defineProps<{
    items: KpiItem[]
    columns?: 2 | 3 | 4
    compact?: boolean
  }>(),
  { columns: 4, compact: false },
)
</script>

<template>
  <section
    class="grid gap-3"
    :class="[
      columns === 2 && 'sm:grid-cols-2',
      columns === 3 && 'sm:grid-cols-2 xl:grid-cols-3',
      columns === 4 && 'sm:grid-cols-2 xl:grid-cols-4',
    ]"
    aria-label="Key figures"
  >
    <GovernStatTile
      v-for="item in items"
      :key="item.label"
      :label="item.label"
      :value="item.value"
      :helper="item.helper"
      :tone="item.tone"
      :compact="compact"
    />
  </section>
</template>
