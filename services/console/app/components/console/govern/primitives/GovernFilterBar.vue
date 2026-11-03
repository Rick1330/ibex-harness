<script setup lang="ts">
import { ref } from "vue"
import { Search, X } from "@lucide/vue"
import KeyHint from "@/components/console/primitives/KeyHint.vue"

const props = withDefaults(
  defineProps<{
    modelValue: string
    placeholder?: string
    label?: string
    resultText?: string
    active?: boolean
  }>(),
  { placeholder: "Search", label: "Search", resultText: "", active: false },
)

const emit = defineEmits<{
  "update:modelValue": [value: string]
  clear: []
  submit: []
}>()

const input = ref<HTMLInputElement | null>(null)

function focus(): void {
  input.value?.focus()
  input.value?.select()
}

defineExpose({ focus })
</script>

<template>
  <div class="flex flex-wrap items-center gap-2">
    <div class="relative w-full min-w-0 sm:w-72">
      <Search :size="13" :stroke-width="1.9" class="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-fg-3" aria-hidden="true" />
      <input
        ref="input"
        :value="props.modelValue"
        type="search"
        :placeholder="placeholder"
        :aria-label="label"
        class="ix-input h-8 pr-9 pl-8 text-xs"
        @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
        @keydown.enter.prevent="emit('submit')"
      >
      <span class="pointer-events-none absolute inset-y-0 right-2 flex items-center"><KeyHint>/</KeyHint></span>
    </div>

    <slot name="filters" />

    <button
      v-if="active"
      type="button"
      class="inline-flex h-8 items-center gap-1 rounded-md px-2 text-xs text-fg-3 transition-colors hover:bg-surface-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
      @click="emit('clear')"
    >
      <X :size="12" :stroke-width="2" aria-hidden="true" />
      Clear
    </button>

    <div class="ml-auto flex shrink-0 flex-wrap items-center gap-2 text-[0.6875rem] leading-4 text-fg-3">
      <span v-if="resultText">{{ resultText }}</span>
      <slot name="right" />
    </div>
  </div>
</template>
