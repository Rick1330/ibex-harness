<script setup lang="ts">
import { ChevronDown } from "@lucide/vue"
import {
  SESSION_DURATION_LABELS,
  type SessionDurationBand,
  type SessionEnvironment,
  type SessionListState,
  type SessionOutcome,
  type SessionTier,
} from "@/lib/session-list-query"

type Option<T extends string> = { label: T; count: number }

const props = defineProps<{
  environments: Option<SessionEnvironment>[]
  outcomes: Option<SessionOutcome>[]
  tiers: readonly SessionTier[]
  agents: string[]
}>()

const state = defineModel<SessionListState>("state", { required: true })

function patch(partial: Partial<SessionListState>): void {
  state.value = { ...state.value, ...partial }
}

function toggleEnvironment(label: SessionEnvironment): void {
  const current = state.value.environments
  patch({
    environments: current.includes(label) ? current.filter((value) => value !== label) : [...current, label],
  })
}

function toggleOutcome(label: SessionOutcome): void {
  const current = state.value.outcomes
  patch({
    outcomes: current.includes(label) ? current.filter((value) => value !== label) : [...current, label],
  })
}

function setTier(tier: SessionTier | ""): void {
  patch({ tier })
}

function setDuration(value: string): void {
  patch({ duration: value as SessionDurationBand | "" })
}

function envDotClass(env: SessionEnvironment): string {
  if (env === "production") return "bg-ok"
  if (env === "staging") return "bg-warn"
  return "bg-fg-off"
}

function outcomeDotClass(outcome: SessionOutcome): string {
  if (outcome === "succeeded") return "bg-ok"
  if (outcome === "denied") return "bg-warn"
  return "bg-crit"
}
</script>

<template>
  <div class="divide-y divide-line-subtle">
    <details open class="group px-3 py-2.5">
      <summary class="flex cursor-pointer list-none items-center justify-between gap-2 text-xs font-medium text-fg-1 [&::-webkit-details-marker]:hidden">
        <span class="flex items-center gap-1.5">
          Environment
          <span v-if="state.environments.length" class="text-fg-3">· {{ state.environments.length }}</span>
        </span>
        <ChevronDown :size="13" :stroke-width="1.75" class="text-fg-3 transition-transform group-open:rotate-180" aria-hidden="true" />
      </summary>
      <div class="mt-2 space-y-0.5">
        <label
          v-for="environment in props.environments"
          :key="environment.label"
          class="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-xs text-fg-2 transition-colors hover:bg-raised"
        >
          <input
            type="checkbox"
            class="size-3.5 rounded border-line accent-[var(--ix-accent)]"
            :checked="state.environments.includes(environment.label)"
            @change="toggleEnvironment(environment.label)"
          >
          <span class="size-1.5 rounded-full" :class="envDotClass(environment.label)" aria-hidden="true" />
          <span class="min-w-0 flex-1 truncate capitalize">{{ environment.label }}</span>
          <span class="font-mono text-[0.6875rem] text-fg-3 tabular-nums">{{ environment.count }}</span>
        </label>
      </div>
    </details>

    <details open class="group px-3 py-2.5">
      <summary class="flex cursor-pointer list-none items-center justify-between gap-2 text-xs font-medium text-fg-1 [&::-webkit-details-marker]:hidden">
        <span class="flex items-center gap-1.5">
          Outcome
          <span v-if="state.outcomes.length" class="text-fg-3">· {{ state.outcomes.length }}</span>
        </span>
        <ChevronDown :size="13" :stroke-width="1.75" class="text-fg-3 transition-transform group-open:rotate-180" aria-hidden="true" />
      </summary>
      <div class="mt-2 space-y-0.5">
        <label
          v-for="outcome in props.outcomes"
          :key="outcome.label"
          class="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-xs text-fg-2 transition-colors hover:bg-raised"
        >
          <input
            type="checkbox"
            class="size-3.5 rounded border-line accent-[var(--ix-accent)]"
            :checked="state.outcomes.includes(outcome.label)"
            @change="toggleOutcome(outcome.label)"
          >
          <span class="size-1.5 rounded-full" :class="outcomeDotClass(outcome.label)" aria-hidden="true" />
          <span class="min-w-0 flex-1 truncate capitalize">{{ outcome.label }}</span>
          <span class="font-mono text-[0.6875rem] text-fg-3 tabular-nums">{{ outcome.count }}</span>
        </label>
      </div>
    </details>

    <details class="group px-3 py-2.5">
      <summary class="flex cursor-pointer list-none items-center justify-between gap-2 text-xs font-medium text-fg-1 [&::-webkit-details-marker]:hidden">
        <span class="flex items-center gap-1.5">
          Tier
          <span v-if="state.tier" class="text-fg-3">· {{ state.tier }}</span>
        </span>
        <ChevronDown :size="13" :stroke-width="1.75" class="text-fg-3 transition-transform group-open:rotate-180" aria-hidden="true" />
      </summary>
      <div class="mt-2 flex flex-wrap gap-1">
        <button
          type="button"
          class="rounded border px-2 py-1 font-mono text-[0.6875rem] transition-colors"
          :class="state.tier === '' ? 'border-accent/40 bg-accent/10 text-accent' : 'border-line-subtle text-fg-3 hover:text-fg-1'"
          :aria-pressed="state.tier === ''"
          @click="setTier('')"
        >
          Any
        </button>
        <button
          v-for="tier in props.tiers"
          :key="tier"
          type="button"
          class="rounded border px-2 py-1 font-mono text-[0.6875rem] transition-colors"
          :class="state.tier === tier ? 'border-accent/40 bg-accent/10 text-accent' : 'border-line-subtle text-fg-3 hover:text-fg-1'"
          :aria-pressed="state.tier === tier"
          @click="setTier(tier)"
        >
          {{ tier }}
        </button>
      </div>
    </details>

    <details class="group px-3 py-2.5">
      <summary class="flex cursor-pointer list-none items-center justify-between gap-2 text-xs font-medium text-fg-1 [&::-webkit-details-marker]:hidden">
        <span class="flex items-center gap-1.5">
          Agent
          <span v-if="state.agent" class="min-w-0 truncate text-fg-3">· {{ state.agent }}</span>
        </span>
        <ChevronDown :size="13" :stroke-width="1.75" class="text-fg-3 transition-transform group-open:rotate-180" aria-hidden="true" />
      </summary>
      <select
        :value="state.agent"
        class="mt-2 h-8 w-full rounded border border-line-subtle bg-canvas/50 px-2 text-xs text-fg-2 focus:border-accent focus:outline-none"
        aria-label="Filter by agent"
        @change="patch({ agent: ($event.target as HTMLSelectElement).value })"
      >
        <option value="">All agents</option>
        <option v-for="agent in props.agents" :key="agent" :value="agent">{{ agent }}</option>
      </select>
    </details>

    <details class="group px-3 py-2.5">
      <summary class="flex cursor-pointer list-none items-center justify-between gap-2 text-xs font-medium text-fg-1 [&::-webkit-details-marker]:hidden">
        <span class="flex items-center gap-1.5">
          Session ID
          <span v-if="state.id" class="font-mono text-fg-3">· {{ state.id }}</span>
        </span>
        <ChevronDown :size="13" :stroke-width="1.75" class="text-fg-3 transition-transform group-open:rotate-180" aria-hidden="true" />
      </summary>
      <input
        :value="state.id"
        type="text"
        class="mt-2 h-8 w-full rounded border border-line-subtle bg-canvas/50 px-2 font-mono text-[0.75rem] text-fg-2 placeholder:text-fg-3 focus:border-accent focus:outline-none"
        placeholder="ses_…"
        aria-label="Filter by session ID"
        @input="patch({ id: ($event.target as HTMLInputElement).value })"
      >
    </details>

    <details class="group px-3 py-2.5">
      <summary class="flex cursor-pointer list-none items-center justify-between gap-2 text-xs font-medium text-fg-1 [&::-webkit-details-marker]:hidden">
        <span class="flex items-center gap-1.5">
          Duration
          <span v-if="state.duration" class="text-fg-3">· {{ SESSION_DURATION_LABELS[state.duration] }}</span>
        </span>
        <ChevronDown :size="13" :stroke-width="1.75" class="text-fg-3 transition-transform group-open:rotate-180" aria-hidden="true" />
      </summary>
      <select
        :value="state.duration"
        class="mt-2 h-8 w-full rounded border border-line-subtle bg-canvas/50 px-2 text-xs text-fg-2 focus:border-accent focus:outline-none"
        aria-label="Filter by duration"
        @change="setDuration(($event.target as HTMLSelectElement).value)"
      >
        <option value="">Any duration</option>
        <option v-for="(label, value) in SESSION_DURATION_LABELS" :key="value" :value="value">{{ label }}</option>
      </select>
    </details>
  </div>
</template>
