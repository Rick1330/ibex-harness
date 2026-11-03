<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue"
import type { PublicOperatorTraceDetail } from "~~/shared/operator/public"
import { Check, Copy } from "@lucide/vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import { EXPLORE_TRACE_DETAIL_CONTRACT } from "@/lib/explore-view"

const props = defineProps<{ detail: PublicOperatorTraceDetail }>()

const payload = computed(() => JSON.stringify(props.detail, null, 2))
const copied = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null

async function copy(): Promise<void> {
  if (!import.meta.client) return
  try {
    await navigator.clipboard.writeText(payload.value)
    copied.value = true
  } catch {
    copied.value = false
  }
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
  <section class="min-w-0" aria-label="Raw record">
    <div class="min-w-0 overflow-hidden rounded-lg border border-line-subtle bg-surface">
      <div class="flex flex-wrap items-center justify-between gap-2 border-b border-line-subtle px-3.5 py-2">
        <p class="font-mono text-[0.6875rem] leading-4 text-fg-3">{{ EXPLORE_TRACE_DETAIL_CONTRACT }}</p>
        <button type="button" class="ix-button-secondary h-7 gap-1 px-2 text-xs" @click="copy">
          <Check v-if="copied" :size="12" :stroke-width="2" aria-hidden="true" />
          <Copy v-else :size="12" :stroke-width="1.8" aria-hidden="true" />
          {{ copied ? "Copied" : "Copy payload" }}
        </button>
      </div>
      <pre
        class="ix-scroll max-h-[34rem] overflow-auto bg-raised p-3 font-mono text-xs leading-4 text-fg-2"
        tabindex="0"
        aria-label="Raw run detail payload"
      >{{ payload }}</pre>
    </div>

    <GovernCaveat class="mt-2" tone="info" title="This is the parsed payload, not the wire bytes">
      The object above is what the console validated against the detail schema and rendered everywhere else on this page.
      Where the schema carries a default, an omitted field appears here as that default rather than as a gap, so
      <code class="font-mono text-fg-2">unavailable_sections</code> — not a missing key — is the contract's own statement
      of what it could not supply.
    </GovernCaveat>
  </section>
</template>
