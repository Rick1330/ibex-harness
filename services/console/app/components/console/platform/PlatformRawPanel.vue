<script setup lang="ts">
import { computed } from "vue"
import type { PublicPlatformHealth } from "~~/shared/operator/public"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import { PLATFORM_CONTRACT } from "@/lib/platform-view"

const props = defineProps<{
  health: PublicPlatformHealth | null
}>()

const emit = defineEmits<{ retry: [] }>()

const rawPayload = computed(() => (props.health ? JSON.stringify(props.health, null, 2) : ""))
</script>

<template>
  <section class="flex min-w-0 flex-col gap-3" aria-label="Snapshot payload">
    <div v-if="!props.health" class="rounded-lg border border-line-subtle bg-surface p-1">
      <GovernEmptyState
        title="No payload to show"
        reason="The health read did not resolve, so there is no validated snapshot to print. The console does not display an unvalidated body."
        action-label="Re-read"
        @action="emit('retry')"
      />
    </div>

    <template v-else>
      <div class="flex flex-wrap items-center justify-between gap-2">
        <p class="text-[0.6875rem] text-fg-3">
          The exact object this page was built from, after contract validation.
          <span class="font-mono">{{ PLATFORM_CONTRACT }}</span>
        </p>
        <GovernCopyId :id="rawPayload" label="snapshot payload" icon-only />
      </div>

      <pre
        class="ix-scroll max-h-[26rem] min-w-0 overflow-auto rounded-lg border border-line-subtle bg-raised p-3.5 font-mono text-[0.6875rem] leading-4 text-fg-2"
        tabindex="0"
        aria-label="Raw platform snapshot payload"
        >{{ rawPayload }}</pre>

      <GovernCaveat tone="lock" title="What is not in this body">
        The organization identifier is stripped before the payload reaches the browser, and no tenant record, memory
        content, prompt, or credential is ever part of this contract. A field that the platform did not report appears
        here as <code class="font-mono">null</code> — which is the same absence the other tabs read, printed without
        interpretation.
      </GovernCaveat>
    </template>
  </section>
</template>
