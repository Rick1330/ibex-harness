<script setup lang="ts">
import { computed } from "vue"
import { formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"
import { formatLiveRelative } from "@/lib/live-format"

const props = withDefaults(
  defineProps<{
    value: string | null | undefined
    /** Wall clock for live surfaces. Omit on fixture-backed pages. */
    now?: number | null
    /** Render the absolute UTC stamp instead of the relative label. */
    absolute?: boolean
    fallback?: string
  }>(),
  { now: null, absolute: false, fallback: "—" },
)

const label = computed(() => {
  if (!props.value) return props.fallback
  if (props.absolute) return formatGovernStamp(props.value)
  return props.now === null ? formatGovernRelative(props.value) : formatLiveRelative(props.value, props.now)
})

const stamp = computed(() => (props.value ? formatGovernStamp(props.value) : undefined))
</script>

<template>
  <time :datetime="value ?? undefined" :title="absolute ? undefined : stamp" class="tabular-nums">
    {{ label }}
  </time>
</template>
