<script setup lang="ts">
import { computed } from "vue"

const props = withDefaults(
  defineProps<{
    tabs: { id: string; label: string }[]
    modelValue: string
    ariaLabel?: string
    badges?: Record<string, string>
  }>(),
  { ariaLabel: "Sections", badges: () => ({}) },
)

const emit = defineEmits<{ "update:modelValue": [value: string] }>()

const currentIndex = computed(() => props.tabs.findIndex((tab) => tab.id === props.modelValue))

function select(id: string): void {
  if (id !== props.modelValue) emit("update:modelValue", id)
}

function onKeydown(event: KeyboardEvent): void {
  if (props.tabs.length === 0) return
  const index = currentIndex.value < 0 ? 0 : currentIndex.value
  let next = index
  if (event.key === "ArrowRight" || event.key === "]") next = (index + 1) % props.tabs.length
  else if (event.key === "ArrowLeft" || event.key === "[") next = (index - 1 + props.tabs.length) % props.tabs.length
  else if (event.key === "Home") next = 0
  else if (event.key === "End") next = props.tabs.length - 1
  else return
  event.preventDefault()
  const tab = props.tabs[next]
  if (!tab) return
  select(tab.id)
  const target = document.getElementById(`govern-tab-${tab.id}`)
  target?.focus()
}
</script>

<template>
  <div class="ix-scroll flex items-center gap-1 overflow-x-auto overflow-y-hidden border-b border-line-subtle" role="tablist" :aria-label="ariaLabel" @keydown="onKeydown">
    <button
      v-for="tab in tabs"
      :id="`govern-tab-${tab.id}`"
      :key="tab.id"
      type="button"
      role="tab"
      :aria-selected="tab.id === modelValue"
      :tabindex="tab.id === modelValue ? 0 : -1"
      class="-mb-px inline-flex h-10 shrink-0 items-center gap-1.5 border-b-2 px-3 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-accent"
      :class="
        tab.id === modelValue
          ? 'border-accent text-fg-1'
          : 'border-transparent text-fg-3 hover:border-line hover:text-fg-1'
      "
      @click="select(tab.id)"
    >
      {{ tab.label }}
      <span
        v-if="badges[tab.id]"
        class="rounded-full border border-line-subtle bg-raised px-1.5 font-mono text-[0.625rem] leading-4 text-fg-3 tabular-nums"
      >{{ badges[tab.id] }}</span>
    </button>
  </div>
</template>
