<script setup lang="ts">
import { computed, onMounted, ref } from "vue"

const props = withDefaults(
  defineProps<{
    /** Value between 0 and 1. */
    value: number
    /** Optional threshold tick position between 0 and 1. */
    threshold?: number | null
    /** Token color class for the filled segment, e.g. "bg-memory". */
    color?: string
    label?: string
    /** "sm" keeps the bar inside dense table columns; "md" is the detail-view size. */
    size?: "sm" | "md"
  }>(),
  { threshold: null, color: "bg-memory", label: undefined, size: "md" },
)

const clamped = computed(() => Math.min(1, Math.max(0, props.value)))
const mounted = ref(false)
onMounted(() => {
  requestAnimationFrame(() => {
    mounted.value = true
  })
})
</script>

<template>
  <span
    class="relative inline-flex h-1.5 w-full min-w-16 overflow-hidden rounded-full bg-raised"
    role="img"
    :aria-label="label ?? `Score ${(value).toFixed(2)} of 1.00`"
  >
    <span
      class="absolute inset-y-0 left-0 rounded-full transition-[width] duration-300 ease-out"
      :class="color"
      :style="{ width: mounted ? `${Math.max(clamped * 100, 2)}%` : '0%' }"
    />
    <span
      v-if="threshold !== null && threshold !== undefined"
      class="absolute inset-y-[-2px] w-px bg-fg-3"
      :style="{ left: `${Math.min(100, Math.max(0, threshold * 100))}%` }"
      aria-hidden="true"
    />
  </span>
</template>
