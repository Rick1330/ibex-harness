<script setup lang="ts">
import { computed } from "vue"
import { ChevronDown } from "@lucide/vue"

const props = withDefaults(
  defineProps<{
    label: string
    modelValue: string
    options: { value: string; label: string }[]
    defaultValue?: string | null
  }>(),
  { defaultValue: null },
)

const emit = defineEmits<{ "update:modelValue": [value: string] }>()

const active = computed(() => props.defaultValue === null || props.modelValue !== props.defaultValue)
</script>

<template>
  <label
    class="relative inline-flex h-8 min-w-0 items-center gap-1 rounded-full border px-2.5 text-xs transition-colors"
    :class="active ? 'border-accent/40 bg-accent-tint text-fg-1' : 'border-line-subtle bg-surface-1 text-fg-3 hover:border-line'"
  >
    <span class="shrink-0 text-fg-3">{{ label }}:</span>
    <select
      :value="modelValue"
      :aria-label="`Filter by ${label.toLowerCase()}`"
      class="cursor-pointer appearance-none bg-transparent pr-4 font-medium text-current outline-none"
      @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
    >
      <option v-for="option in options" :key="option.value" :value="option.value">{{ option.label }}</option>
    </select>
    <ChevronDown :size="11" :stroke-width="2" class="pointer-events-none absolute right-2 text-fg-3" aria-hidden="true" />
  </label>
</template>
