<script setup lang="ts">
import { computed } from "vue"
import { ChevronDown, Info } from "@lucide/vue"

type DataSourceState = "live" | "partial" | "illustrative"

const props = withDefaults(
  defineProps<{
    /** Legacy boolean kept for existing pages. Prefer `state`. */
    live?: boolean
    state?: DataSourceState
  }>(),
  { live: false, state: undefined },
)

const emit = defineEmits<{ open: [] }>()

const resolved = computed<DataSourceState>(() => props.state ?? (props.live ? "live" : "illustrative"))

const label = computed(() => {
  switch (resolved.value) {
    case "live":
      return "Live"
    case "partial":
      return "Partial"
    default:
      return "Illustrative"
  }
})

const tone = computed(() => {
  switch (resolved.value) {
    case "live":
      return "border-line bg-transparent text-fg-2 hover:border-line-strong"
    case "partial":
      return "border-line bg-transparent text-fg-2 hover:border-line-strong"
    default:
      return "border-line bg-transparent text-fg-2 hover:border-line-strong"
  }
})
</script>

<template>
  <button
    type="button"
    class="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full border px-2 text-[0.6875rem] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
    :class="tone"
    :aria-label="`About this data: ${label.toLowerCase()}`"
    @click="emit('open')"
  >
    <span
      class="size-1.5 rounded-full"
      :class="resolved === 'live' ? 'bg-ok' : resolved === 'partial' ? 'border border-warn bg-transparent' : 'bg-warn'"
      aria-hidden="true"
    />
    {{ label }}
    <ChevronDown :size="11" :stroke-width="1.9" aria-hidden="true" />
    <Info class="sr-only" :size="12" aria-hidden="true" />
  </button>
</template>
