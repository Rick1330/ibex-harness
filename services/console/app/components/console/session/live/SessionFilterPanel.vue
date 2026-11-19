<script setup lang="ts">
import { computed } from "vue"
import { X } from "@lucide/vue"
import {
  SESSION_DURATION_OPTIONS,
  SESSION_STATUS_LABELS,
  activeSessionFilterCount,
  type SessionDurationBucket,
  type SessionFilterOption,
  type SessionPageFilters,
} from "@/lib/session-list"
import type { SessionStatus } from "~~/shared/operator/contracts"

const props = defineProps<{
  scope: { status: SessionStatus | null; agentId: string | null }
  options: { agents: SessionFilterOption[]; models: string[]; providers: string[] }
  filters: SessionPageFilters
}>()

const emit = defineEmits<{
  agent: [value: string | null]
  status: [value: null]
  page: [patch: Partial<SessionPageFilters>]
  clear: []
}>()

const activeCount = computed(() => activeSessionFilterCount(props.filters, props.scope))

const linkedStatus = computed(() => (props.scope.status === null ? "" : SESSION_STATUS_LABELS[props.scope.status]))

function readSelect(event: Event): string | null {
  const value = (event.target as HTMLSelectElement).value
  return value === "" ? null : value
}

function onAgent(event: Event): void {
  emit("agent", readSelect(event))
}

function onModel(event: Event): void {
  emit("page", { model: readSelect(event) })
}

function onProvider(event: Event): void {
  emit("page", { provider: readSelect(event) })
}

function onDuration(event: Event): void {
  emit("page", { duration: readSelect(event) as SessionDurationBucket | null })
}
</script>

<template>
  <aside
    id="session-filters"
    class="flex min-w-0 flex-col gap-4 rounded-lg border border-line-subtle bg-surface p-3"
    aria-label="Session filters"
  >
    <div class="flex items-center justify-between gap-2">
      <h2 class="ix-heading text-fg-1">Filters</h2>
      <button
        v-if="activeCount > 0"
        type="button"
        class="inline-flex items-center gap-1 rounded px-1 text-[0.6875rem] text-fg-3 transition-colors hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
        @click="emit('clear')"
      >
        <X :size="11" :stroke-width="2" aria-hidden="true" />
        Clear {{ activeCount }}
      </button>
    </div>

    <div class="flex min-w-0 flex-col gap-2.5">
      <h3 class="text-[0.6875rem] font-medium tracking-wide text-fg-3 uppercase">Narrows the request</h3>
      <label class="flex min-w-0 flex-col gap-1">
        <span class="ix-label">Agent</span>
        <select class="ix-input" :value="scope.agentId ?? ''" @change="onAgent">
          <option value="">Any agent</option>
          <option v-for="option in options.agents" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
      </label>
    </div>

    <div class="flex min-w-0 flex-col gap-2.5 border-t border-line-subtle pt-3">
      <h3 class="text-[0.6875rem] font-medium tracking-wide text-fg-3 uppercase">Narrows this page</h3>
      <label class="flex min-w-0 flex-col gap-1">
        <span class="ix-label">Model</span>
        <select class="ix-input" :value="filters.model ?? ''" @change="onModel">
          <option value="">Any model</option>
          <option v-for="model in options.models" :key="model" :value="model">{{ model }}</option>
        </select>
      </label>

      <label class="flex min-w-0 flex-col gap-1">
        <span class="ix-label">Provider</span>
        <select class="ix-input" :value="filters.provider ?? ''" @change="onProvider">
          <option value="">Any provider</option>
          <option v-for="provider in options.providers" :key="provider" :value="provider">{{ provider }}</option>
        </select>
      </label>

      <label class="flex min-w-0 flex-col gap-1">
        <span class="ix-label">Turn latency</span>
        <select class="ix-input" :value="filters.duration ?? ''" @change="onDuration">
          <option value="">Any latency</option>
          <option v-for="option in SESSION_DURATION_OPTIONS" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>
    </div>

    <div
      v-if="scope.status"
      class="flex items-start justify-between gap-2 rounded-md border border-line-subtle bg-surface-2 px-2 py-1.5"
    >
      <span class="text-[0.6875rem] leading-4 text-fg-2">
        This link limits the read to <span class="font-medium text-fg-1">{{ linkedStatus }}</span> sessions only.
      </span>
      <button
        type="button"
        class="mt-0.5 inline-flex size-4 shrink-0 items-center justify-center rounded text-fg-3 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
        aria-label="Remove the linked outcome filter"
        @click="emit('status', null)"
      >
        <X :size="11" :stroke-width="2" aria-hidden="true" />
      </button>
    </div>
  </aside>
</template>
