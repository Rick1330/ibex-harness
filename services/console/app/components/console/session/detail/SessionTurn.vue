<script setup lang="ts">
import { computed, ref } from "vue"
import {
  ArrowRight,
  Check,
  ChevronRight,
  Copy,
  TriangleAlert,
  UserRound,
} from "@lucide/vue"
import { memoryAgentIndex } from "@/lib/memory-list"
import BrandIcon from "@/components/console/BrandIcon.vue"
import type { PreviewSession, SessionFocus, SessionRound } from "@/lib/session-preview"
import {
  formatOffset,
  outcomeLabel,
  outcomeTone,
  parseCostUsd,
  formatCostShort,
  roundFailureMessage,
  roundOffsetMs,
  stepRows,
} from "@/lib/session-detail"
import SessionCaveat from "./primitives/SessionCaveat.vue"
import SessionStatusPill from "./primitives/SessionStatusPill.vue"
import SessionStep from "./SessionStep.vue"

const props = defineProps<{
  session: PreviewSession
  round: SessionRound
  selected: boolean
  expandAll: boolean
  expandKey: number
  highlightStepId: string | null
  returnTo: string
  copiedKey: string | null
}>()

const emit = defineEmits<{
  select: [index: number]
  inspect: [panel: SessionFocus, spanId: string | null]
  copy: [value: string, label: string]
}>()

const thoughtOpen = ref(false)
const steps = computed(() => stepRows(props.round))
const offset = computed(() => roundOffsetMs(props.session, props.round))
const failure = computed(() => roundFailureMessage(props.round))
const agentIndex = computed(() => memoryAgentIndex(props.session.agent))
const agentInitials = computed(() =>
  props.session.agent
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join(""),
)
const agentStyle = computed(() => ({
  backgroundColor: `color-mix(in oklch, var(--ix-agent-${agentIndex.value}) 16%, transparent)`,
  color: "var(--ix-fg-1)",
}))
const tone = computed(() => outcomeTone(props.round.outcome))
const driftReason = computed(() => props.round.drift?.detail?.trim() || "Advisory raised; no reason recorded.")
const traceShort = computed(() => props.round.traceId.replace(/^trc_/, ""))
const costShort = computed(() => formatCostShort(parseCostUsd(props.round.cost)))

function select(): void {
  emit("select", props.round.index)
}

function inspect(panel: SessionFocus, spanId: string | null = null): void {
  emit("inspect", panel, spanId)
}

function onThoughtToggle(event: Event): void {
  thoughtOpen.value = (event.target as HTMLDetailsElement).open
}
</script>

<template>
  <article
    :id="`turn-${round.index}`"
    :data-turn-index="round.index"
    class="ix-turn"
    :class="selected && 'ix-turn-selected'"
    :aria-labelledby="`turn-${round.index}-heading`"
    @click="select"
  >
    <!-- Customer message -->
    <div class="ix-message">
      <div class="ix-gutter">
        <span class="ix-avatar ix-avatar-customer" aria-hidden="true">
          <UserRound :size="14" :stroke-width="1.8" />
        </span>
        <span class="font-mono text-[0.625rem] leading-4 text-fg-3 tabular-nums">{{ formatOffset(offset) }}</span>
      </div>
      <div class="min-w-0">
        <p class="mb-1.5 flex items-center gap-1.5 text-[0.6875rem] leading-4 font-medium text-fg-3">
          Customer
          <span class="sr-only">, turn {{ round.index }}</span>
        </p>
        <div class="rounded-lg border border-line-subtle bg-surface-1 px-4 py-3">
          <p class="max-w-[68ch] text-[0.9375rem] leading-6 text-fg-1 text-pretty">{{ round.userText }}</p>
        </div>
      </div>
    </div>

    <!-- Agent response -->
    <div class="ix-message mt-4">
      <div class="ix-gutter">
        <span class="ix-avatar" :style="agentStyle" aria-hidden="true">{{ agentInitials }}</span>
        <span class="font-mono text-[0.625rem] leading-4 text-fg-3 tabular-nums">{{ formatOffset(offset) }}</span>
      </div>
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
          <h3 :id="`turn-${round.index}-heading`" class="text-[0.8125rem] leading-5 font-semibold text-fg-1">
            {{ session.agent }}
          </h3>
          <span class="inline-flex items-center gap-1 text-xs leading-4 text-fg-3"><BrandIcon :id="round.model" :size="12" :label="`${round.model} logo`" />{{ round.model }}</span>
          <span class="text-fg-off" aria-hidden="true">·</span>
          <span class="font-mono text-[0.6875rem] leading-4 text-fg-3 tabular-nums">{{ round.latencyMs }} ms</span>
          <SessionStatusPill class="ml-auto" :tone="tone" :label="outcomeLabel(round.outcome)" />
        </div>

        <div v-if="failure" class="mt-2.5 rounded-lg border border-crit/30 bg-crit-tint px-3 py-2.5">
          <p class="flex items-start gap-2 text-[0.8125rem] leading-5 text-fg-1">
            <TriangleAlert :size="14" :stroke-width="1.9" class="mt-0.5 shrink-0 text-crit" aria-hidden="true" />
            <span><span class="font-medium">This turn failed.</span> {{ failure }}</span>
          </p>
          <button
            type="button"
            class="mt-1.5 ml-5 rounded text-[0.6875rem] leading-4 font-medium text-fg-2 underline decoration-line-strong underline-offset-2 hover:text-fg-1"
            @click.stop="inspect('trace')"
          >
            Open the failing span in Trace
          </button>
        </div>

        <details class="ix-thought group/thought mt-1.5" @click.stop @toggle="onThoughtToggle">
          <summary class="ix-thought-trigger">
            <ChevronRight :size="12" :stroke-width="2" class="ix-thought-chevron" aria-hidden="true" />
            <span class="text-[0.8125rem] text-fg-3">Thought</span>
            <span class="font-mono text-[0.6875rem] text-fg-3 tabular-nums">{{ round.latencyMs }} ms</span>
          </summary>
          <p class="mt-1.5 ml-5 max-w-[68ch] border-l border-line pl-3 text-[0.8125rem] leading-6 text-fg-2 text-pretty">{{ round.reasoning }}</p>
        </details>

        <p class="mt-3 max-w-[68ch] text-[0.9375rem] leading-[1.6] text-fg-1 text-pretty">{{ round.assistantText }}</p>

        <div
          v-if="round.drift"
          class="mt-4 rounded-lg border border-warn/30 bg-warn-tint px-3.5 py-3"
        >
          <p class="flex items-start gap-2 text-[0.8125rem] leading-5 text-fg-1 text-pretty">
            <TriangleAlert :size="14" :stroke-width="1.9" class="mt-0.5 shrink-0 text-warn" aria-hidden="true" />
            <span>
              <span class="font-medium">Drift advisory:</span>
              <span :class="!round.drift.detail && 'text-fg-3'">&nbsp;{{ driftReason }}</span>
            </span>
          </p>
          <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 pl-5">
            <SessionCaveat
              summary="Why flagged"
              :detail="`${round.drift.signal}. ${round.drift.uncertainty}`"
            />
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded text-[0.6875rem] leading-4 font-medium text-fg-2 transition-colors hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
              @click.stop="inspect('drift')"
            >
              Open in Drift tab
              <ArrowRight :size="11" :stroke-width="1.75" aria-hidden="true" />
            </button>
          </div>
        </div>

        <ul class="mt-3 space-y-1" aria-label="Steps for turn {{ round.index }}">
          <SessionStep
            v-for="step in steps"
            :key="step.id"
            :round="round"
            :step="step"
            :expanded="expandAll"
            :expand-key="expandKey"
            :highlighted="highlightStepId === step.id"
            :return-to="returnTo"
            @inspect="inspect"
          />
        </ul>

        <div class="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1 border-t border-line-subtle pt-2 text-[0.6875rem] leading-4 text-fg-3">
          <span class="font-mono tabular-nums">{{ round.tokensIn }} in · {{ round.tokensOut }} out</span>
          <span aria-hidden="true">·</span>
          <span class="font-mono tabular-nums" :title="round.cost">{{ costShort }}</span>
          <span aria-hidden="true">·</span>
          <span class="group/trace inline-flex items-center gap-1 font-mono">
            trace {{ traceShort }}
            <button
              type="button"
              class="inline-flex size-5 items-center justify-center rounded text-fg-3 opacity-60 transition-[opacity,color,background-color] hover:bg-raised hover:text-fg-1 group-hover/trace:opacity-100 focus-visible:opacity-100"
              :aria-label="copiedKey === `trace-${round.id}` ? 'Trace ID copied' : `Copy trace ID ${round.traceId}`"
              @click.stop="emit('copy', round.traceId, 'Trace ID')"
            >
              <Check v-if="copiedKey === `trace-${round.id}`" :size="11" :stroke-width="2" class="text-ok" aria-hidden="true" />
              <Copy v-else :size="11" :stroke-width="1.75" aria-hidden="true" />
            </button>
          </span>
          <button
            type="button"
            class="ml-auto inline-flex items-center gap-1 rounded px-1 py-0.5 text-[0.75rem] font-medium text-fg-2 transition-colors hover:bg-raised hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            @click.stop="inspect('trace')"
          >
            Inspect
            <ArrowRight :size="11" :stroke-width="1.75" aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  </article>
</template>

<style scoped>
.ix-turn {
  position: relative;
  scroll-margin-top: 8rem;
  border-radius: 10px;
  padding: 0.5rem 0.5rem 0.75rem 0;
  transition: background-color 150ms;
}

.ix-turn::before {
  content: "";
  position: absolute;
  top: 0.5rem;
  bottom: 0.5rem;
  left: -0.5rem;
  width: 2px;
  border-radius: 2px;
  background: transparent;
  transition: background-color 150ms;
}

.ix-turn-selected {
  background: color-mix(in srgb, var(--ix-memory) 3%, transparent);
}

.ix-turn-selected::before {
  background: var(--ix-accent-memory);
}

.ix-message {
  display: grid;
  grid-template-columns: 2.5rem minmax(0, 1fr);
  gap: 0.75rem;
  cursor: pointer;
}

.ix-message a,
.ix-message button,
.ix-message summary {
  cursor: auto;
}

.ix-gutter {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  padding-top: 0.125rem;
}

.ix-avatar {
  display: inline-flex;
  width: 1.75rem;
  height: 1.75rem;
  flex: none;
  align-items: center;
  justify-content: center;
  border-radius: 7px;
  font-size: 0.625rem;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.ix-avatar-customer {
  border: 1px solid var(--ix-line-subtle);
  background: var(--ix-raised);
  color: var(--ix-fg-2);
}

.ix-thought-trigger {
  display: inline-flex;
  cursor: pointer;
  list-style: none;
  align-items: center;
  gap: 0.375rem;
  border-radius: 5px;
  padding: 0.25rem 0.375rem;
  transition: background-color 120ms;
}

.ix-thought-trigger::-webkit-details-marker {
  display: none;
}

.ix-thought-trigger:hover {
  background: var(--ix-raised);
}

.ix-thought-trigger:focus-visible {
  outline: 2px solid var(--ix-accent-memory);
  outline-offset: 2px;
}

.ix-thought-chevron {
  color: var(--ix-fg-3);
  transition: transform 150ms ease-out;
}

.ix-thought[open] .ix-thought-chevron {
  transform: rotate(90deg);
}

@media (max-width: 720px) {
  .ix-turn {
    padding-right: 0;
  }

  .ix-message {
    grid-template-columns: 2rem minmax(0, 1fr);
    gap: 0.5rem;
  }

  .ix-avatar {
    width: 1.5rem;
    height: 1.5rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ix-turn,
  .ix-thought-chevron {
    transition-duration: 1ms;
  }
}
</style>
