<script setup lang="ts">
import { computed } from "vue"
import { RefreshCw } from "@lucide/vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import { formatGovernStamp } from "@/lib/govern-format"
import { formatLiveRelative } from "@/lib/live-format"

const props = withDefaults(
  defineProps<{
    enabled: boolean
    nowMs?: number | null
  }>(),
  { nowMs: null },
)

const { state, connectedAt, lastAttemptAt, attempts, endpoint, reconnect } = useOperatorEventStream(
  () => props.enabled,
)

const STATE_LABEL = {
  connecting: "Connecting",
  connected: "Connected",
  unavailable: "Not connected",
} as const

const STATE_CLASS = {
  connecting: "text-warn",
  connected: "text-ok",
  unavailable: "text-warn",
} as const

const openSince = computed(() => (connectedAt.value === null ? null : new Date(connectedAt.value).toISOString()))
const lastAttempt = computed(() => (lastAttemptAt.value === null ? null : new Date(lastAttemptAt.value).toISOString()))
</script>

<template>
  <div class="rounded-lg border border-line-subtle bg-surface px-3.5 py-3" :data-stream-state="state">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h3 class="text-xs font-medium text-fg-1">Event stream</h3>
      <button
        type="button"
        class="ix-button-secondary"
        :disabled="state === 'connecting'"
        :title="state === 'connecting' ? 'A connection attempt is already in flight.' : 'Close this stream and open a new one'"
        @click="reconnect"
      >
        <RefreshCw :size="13" :stroke-width="1.75" aria-hidden="true" />
        Reconnect
      </button>
    </div>

    <p class="mt-1 text-[0.6875rem] leading-4" :class="STATE_CLASS[state]">
      {{ STATE_LABEL[state] }}
      <span v-if="state === 'connected' && openSince" class="font-mono text-fg-3" :title="formatGovernStamp(openSince)">
        · open since {{ formatLiveRelative(openSince, props.nowMs) }}
      </span>
    </p>

    <dl class="mt-2 space-y-1.5 text-xs">
      <div class="flex items-baseline justify-between gap-3">
        <dt class="shrink-0 text-fg-3">Endpoint</dt>
        <dd class="min-w-0 truncate text-right font-mono text-[0.6875rem] text-fg-2" :title="endpoint">{{ endpoint }}</dd>
      </div>
      <div class="flex items-baseline justify-between gap-3">
        <dt class="text-fg-3">Attempts this view</dt>
        <dd class="font-mono text-[0.6875rem] tabular-nums text-fg-2">{{ attempts }}</dd>
      </div>
      <div class="flex items-baseline justify-between gap-3">
        <dt class="text-fg-3">Last attempt</dt>
        <dd class="font-mono text-[0.6875rem] whitespace-nowrap text-fg-2">
          {{ lastAttempt ? formatLiveRelative(lastAttempt, props.nowMs) : "No attempt made" }}
        </dd>
      </div>
    </dl>

    <GovernCaveat class="mt-2.5" tone="info" title="Connection state only">
      This panel tracks whether the browser holds an open stream. It does not retain events, and it is not proof that a
      change reached the console: the tables on this page are always the result of a read, never of a push.
    </GovernCaveat>
  </div>
</template>
