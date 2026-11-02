<script setup lang="ts">
import { computed } from "vue"
import { formatGovernStamp } from "@/lib/govern-format"
import { formatLiveRelative } from "@/lib/live-format"

const props = withDefaults(
  defineProps<{
    value: string | null | undefined
    /**
     * The clock this age is measured against. Required: a fixture passes
     * `GOVERN_NOW`, a live surface passes its ticking `nowMs`. There is no
     * default, because inheriting the fixture clock is how live pages showed
     * stale ages.
     */
    now: number
    /** Render the absolute UTC stamp instead of the relative label. */
    absolute?: boolean
    fallback?: string
  }>(),
  { absolute: false, fallback: "—" },
)

const label = computed(() => {
  if (!props.value) return props.fallback
  if (props.absolute) return formatGovernStamp(props.value)
  return formatLiveRelative(props.value, props.now)
})

const stamp = computed(() => (props.value ? formatGovernStamp(props.value) : undefined))
</script>

<template>
  <time :datetime="value ?? undefined" :title="absolute ? undefined : stamp" class="tabular-nums">
    {{ label }}
  </time>
</template>
