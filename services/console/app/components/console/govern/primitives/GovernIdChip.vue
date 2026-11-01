<script setup lang="ts">
import { onBeforeUnmount, ref } from "vue"
import { Check, Copy } from "@lucide/vue"

const props = withDefaults(
  defineProps<{
    value: string
    label?: string
    href?: string | null
    display?: string | null
    copyable?: boolean
  }>(),
  { label: "ID", href: null, display: null, copyable: true },
)

const copied = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null

async function copy(): Promise<void> {
  if (!import.meta.client) return
  try {
    await navigator.clipboard.writeText(props.value)
  } catch {
    return
  }
  copied.value = true
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    copied.value = false
  }, 1_600)
}

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
})
</script>

<template>
  <span class="group/id inline-flex min-w-0 items-center gap-0.5">
    <NuxtLink
      v-if="href"
      :to="href"
      class="min-w-0 break-all font-mono text-[0.6875rem] leading-4 text-fg-2 tabular-nums underline decoration-line-strong underline-offset-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
      :title="value"
    >{{ display ?? value }}</NuxtLink>
    <span
      v-else
      class="min-w-0 break-all font-mono text-[0.6875rem] leading-4 text-fg-2 tabular-nums"
      :title="value"
    >{{ display ?? value }}</span>
    <button
      v-if="copyable"
      type="button"
      class="inline-flex size-5 shrink-0 items-center justify-center rounded text-fg-3 opacity-0 transition-[opacity,color,background-color] hover:bg-raised hover:text-fg-1 group-hover/id:opacity-100 focus-visible:opacity-100 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
      :aria-label="copied ? `${label} copied` : `Copy ${label} ${value}`"
      :title="copied ? 'Copied' : `Copy ${label.toLowerCase()}`"
      @click.stop.prevent="copy"
    >
      <Check v-if="copied" :size="11" :stroke-width="2.2" class="text-ok" aria-hidden="true" />
      <Copy v-else :size="11" :stroke-width="1.8" aria-hidden="true" />
    </button>
    <span class="sr-only" aria-live="polite">{{ copied ? `${label} copied` : "" }}</span>
  </span>
</template>
