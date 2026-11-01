<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue"
import { Check, ChevronRight, Copy } from "@lucide/vue"
import MemoryJsonView from "@/components/console/memory/primitives/MemoryJsonView.vue"

const props = withDefaults(
  defineProps<{
    value: unknown
    label?: string
  }>(),
  { label: "Raw record" },
)

const copied = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null

const lineCount = computed(() => JSON.stringify(props.value, null, 2)?.split("\n").length ?? 0)

async function copy(): Promise<void> {
  try {
    await navigator.clipboard.writeText(JSON.stringify(props.value, null, 2) ?? "null")
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
  <details class="ix-raw group/raw min-w-0">
    <summary class="ix-raw-trigger">
      <ChevronRight :size="12" :stroke-width="2" class="ix-raw-chevron" aria-hidden="true" />
      <span>{{ label }}</span>
      <span class="font-mono text-[0.625rem] text-fg-3 tabular-nums">{{ lineCount }} lines</span>
    </summary>
    <div class="relative mt-1.5">
      <button
        type="button"
        class="ix-raw-copy"
        :aria-label="copied ? 'Raw JSON copied' : 'Copy raw JSON'"
        @click="copy"
      >
        <Check v-if="copied" :size="12" :stroke-width="2" class="text-ok" aria-hidden="true" />
        <Copy v-else :size="12" :stroke-width="1.75" aria-hidden="true" />
      </button>
      <MemoryJsonView :value="value" />
    </div>
  </details>
</template>

<style scoped>
.ix-raw {
  border-top: 1px solid var(--ix-line-subtle);
  padding-top: 0.625rem;
}

.ix-raw-trigger {
  display: inline-flex;
  cursor: pointer;
  list-style: none;
  align-items: center;
  gap: 0.3125rem;
  border-radius: 4px;
  padding: 0.125rem 0.25rem 0.125rem 0;
  font-size: 0.75rem;
  line-height: 1.125rem;
  color: var(--ix-fg-3);
  transition: color 120ms;
}

.ix-raw-trigger::-webkit-details-marker {
  display: none;
}

.ix-raw-trigger:hover {
  color: var(--ix-fg-1);
}

.ix-raw-trigger:focus-visible {
  outline: 2px solid var(--ix-accent);
  outline-offset: 2px;
}

.ix-raw-chevron {
  flex: none;
  transition: transform 150ms ease-out;
}

.ix-raw[open] .ix-raw-chevron {
  transform: rotate(90deg);
}

.ix-raw-copy {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  z-index: 1;
  display: inline-flex;
  width: 1.5rem;
  height: 1.5rem;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--ix-line-subtle);
  border-radius: 5px;
  background: var(--ix-overlay);
  color: var(--ix-fg-3);
  transition: color 120ms, border-color 120ms;
}

.ix-raw-copy:hover {
  border-color: var(--ix-line-strong);
  color: var(--ix-fg-1);
}

.ix-raw-copy:focus-visible {
  outline: 2px solid var(--ix-accent);
  outline-offset: 1px;
}
</style>
