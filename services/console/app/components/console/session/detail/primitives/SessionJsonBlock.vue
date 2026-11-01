<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue"
import { Check, Copy } from "@lucide/vue"
import MemoryJsonView from "@/components/console/memory/primitives/MemoryJsonView.vue"

const props = withDefaults(
  defineProps<{
    label: string
    value: unknown
    maxLines?: number
  }>(),
  { maxLines: 12 },
)

const expanded = ref(false)
const copied = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null

const text = computed(() => JSON.stringify(props.value ?? null, null, 2) ?? "null")
const lines = computed(() => text.value.split("\n"))
const truncated = computed(() => lines.value.length > props.maxLines)
const preview = computed(() => lines.value.slice(0, props.maxLines).join("\n"))

async function copy(): Promise<void> {
  try {
    await navigator.clipboard.writeText(text.value)
    copied.value = true
  } catch {
    copied.value = false
  }
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    copied.value = false
  }, 1_500)
}

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
})
</script>

<template>
  <div class="min-w-0">
    <div class="flex items-center justify-between gap-2">
      <p class="text-[0.6875rem] leading-4 font-medium text-fg-3">{{ label }}</p>
      <button
        type="button"
        class="inline-flex size-6 items-center justify-center rounded text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
        :aria-label="copied ? `${label} copied` : `Copy ${label.toLowerCase()}`"
        @click="copy"
      >
        <Check v-if="copied" :size="12" :stroke-width="2" class="text-ok" aria-hidden="true" />
        <Copy v-else :size="12" :stroke-width="1.75" aria-hidden="true" />
      </button>
    </div>
    <MemoryJsonView v-if="expanded || !truncated" :value="value" />
    <template v-else>
      <pre class="ix-scroll max-h-52 overflow-auto rounded-lg border border-line-subtle bg-raised p-3 font-mono text-xs leading-5 whitespace-pre text-fg-2"><code>{{ preview }}</code></pre>
      <button
        type="button"
        class="mt-1 rounded text-[0.6875rem] leading-4 font-medium text-fg-2 underline decoration-line-strong underline-offset-2 transition-colors hover:text-fg-1"
        @click="expanded = true"
      >
        Show all ({{ lines.length }} lines)
      </button>
    </template>
  </div>
</template>
