<script setup lang="ts">
import { Lock } from "@lucide/vue"
import RelativeTime from "@/components/console/RelativeTime.vue"

withDefaults(
  defineProps<{
    label: string
    hint?: string | null
    value?: string | null
    owner?: string | null
    changedAt?: string | null
    audit?: string | null
    enabled?: boolean | null
    tone?: "default" | "ok" | "warn" | "crit" | "neutral"
    showLock?: boolean
  }>(),
  {
    hint: null,
    value: null,
    owner: null,
    changedAt: null,
    audit: null,
    enabled: null,
    tone: "default",
    showLock: true,
  },
)
</script>

<template>
  <div class="flex flex-wrap items-start justify-between gap-4 px-4 py-3.5">
    <div class="min-w-0 flex-1">
      <p class="text-xs font-medium text-fg-1">{{ label }}</p>
      <p v-if="hint" class="mt-0.5 max-w-[58ch] text-[0.6875rem] leading-4 text-fg-3 text-pretty">{{ hint }}</p>
      <p v-if="owner || changedAt || audit" class="mt-1 flex flex-wrap items-center gap-x-1.5 font-mono text-[0.625rem] leading-4 text-fg-3">
        <span v-if="owner">{{ owner }}</span>
        <template v-if="changedAt">
          <span v-if="owner" aria-hidden="true">·</span>
          <span>changed <RelativeTime :value="changedAt" absolute /></span>
        </template>
        <template v-if="audit">
          <span aria-hidden="true">·</span>
          <NuxtLink :to="`/audit/events/${audit}`" class="ix-link">{{ audit }}</NuxtLink>
        </template>
      </p>
    </div>

    <div class="flex shrink-0 items-center gap-2">
      <slot>
        <span
          v-if="enabled !== null"
          class="inline-flex h-4 w-7 items-center rounded-full border px-0.5 transition-colors"
          :class="enabled ? 'border-accent/40 bg-accent/20' : 'border-line bg-raised'"
          role="img"
          :aria-label="enabled ? 'Enabled' : 'Disabled'"
          :title="enabled ? 'Enabled · read-only console' : 'Disabled · read-only console'"
        >
          <span
            class="block size-3 rounded-full"
            :class="enabled ? 'translate-x-3 bg-accent' : 'translate-x-0 bg-fg-off'"
          />
        </span>
        <span
          v-if="value"
          class="rounded-md border border-line-subtle bg-raised px-2 py-1 font-mono text-[0.6875rem] text-fg-1"
          :class="[
            tone === 'ok' && 'text-ok',
            tone === 'warn' && 'text-warn',
            tone === 'crit' && 'text-crit',
            tone === 'neutral' && 'text-fg-3',
          ]"
        >{{ value }}</span>
        <Lock v-if="showLock && enabled === null" :size="12" :stroke-width="1.8" class="text-fg-off" aria-hidden="true" />
      </slot>
    </div>
  </div>
</template>
