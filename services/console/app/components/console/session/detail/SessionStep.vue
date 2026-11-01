<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ArrowUpRight, ChevronRight, Database } from "@lucide/vue"
import { hasMemoryPreview } from "@/lib/memory-detail-preview"
import { memoryDetailHref } from "@/lib/memory-list-query"
import type { SessionFocus, SessionRound } from "@/lib/session-preview"
import { outcomeTone } from "@/lib/session-detail"
import MemoryOutcomePill from "@/components/console/memory/primitives/MemoryOutcomePill.vue"
import MemoryScoreBar from "@/components/console/memory/primitives/MemoryScoreBar.vue"
import SessionJsonBlock from "./primitives/SessionJsonBlock.vue"
import SessionSpanMark from "./primitives/SessionSpanMark.vue"
import SessionStatusPill from "./primitives/SessionStatusPill.vue"

const props = defineProps<{
  round: SessionRound
  step: {
    id: string
    label: string
    kind: SessionRound["spans"][number]["kind"]
    durationMs: number
    summary: string
    status: "ok" | "error" | "skipped"
    span: SessionRound["spans"][number] | null
    toolCall: SessionRound["toolCalls"][number] | null
  }
  expanded: boolean
  highlighted: boolean
  returnTo: string
}>()

const emit = defineEmits<{
  inspect: [panel: SessionFocus, spanId: string | null]
}>()

const open = ref(props.expanded)
const root = ref<HTMLDetailsElement | null>(null)

watch(
  () => props.expanded,
  (value) => {
    open.value = value
    if (root.value && value) root.value.open = true
    if (root.value && !value) root.value.open = false
  },
)

const kindLabel = computed(() => {
  if (props.step.kind === "llm") return "LLM"
  return props.step.kind.charAt(0).toUpperCase() + props.step.kind.slice(1)
})

const statusTone = computed(() =>
  props.step.status === "ok"
    ? "success"
    : props.step.status === "skipped"
      ? "neutral"
      : "destructive",
)

const statusText = computed(() =>
  props.step.status === "ok" ? "ok" : props.step.status === "skipped" ? "skipped" : "failed",
)

const durationLabel = computed(() =>
  props.step.status === "skipped" ? "—" : `${props.step.durationMs} ms`,
)

const barWidth = computed(() =>
  props.step.status === "skipped" || props.round.latencyMs <= 0
    ? 0
    : Math.max(4, Math.min(100, (props.step.durationMs / props.round.latencyMs) * 100)),
)

const canInspect = computed(() => props.step.span !== null)
const memories = computed(() => props.round.memories)
const hasDetails = computed(() => Boolean(props.step.toolCall || props.step.span))
const inputValue = computed(() =>
  props.step.toolCall?.args ?? props.step.span?.attributes.input ?? null,
)
const outputValue = computed(() =>
  props.step.toolCall?.output ?? props.step.span?.attributes.output ?? null,
)

function toggle(): void {
  open.value = !open.value
  if (root.value) root.value.open = open.value
}

function inspect(panel: SessionFocus = "trace"): void {
  emit("inspect", panel, props.step.span?.id ?? null)
}

function stepPanel(): SessionFocus {
  if (props.step.label === "memory.retrieve") return "memories"
  if (props.step.label === "policy.check") return "policy"
  return "trace"
}
</script>

<template>
  <li
    class="ix-step"
    :class="highlighted && 'ix-step-highlight'"
    :data-step-id="step.id"
  >
    <details ref="root" :open="open" class="ix-step-details">
      <summary
        class="ix-step-row"
        :aria-label="`${step.label}. ${step.summary}. ${statusText}. ${durationLabel}. ${open ? 'Collapse details' : 'Expand details'}`"
        @click.prevent="toggle"
      >
        <ChevronRight :size="12" :stroke-width="2" class="ix-step-chevron" aria-hidden="true" />
        <SessionSpanMark :kind="step.kind" />
        <span class="ix-step-name" :title="step.label">{{ step.label }}</span>
        <span class="min-w-0 flex-1 truncate text-[0.8125rem] leading-5 text-fg-3">{{ step.summary }}</span>
        <SessionStatusPill :tone="statusTone" :label="statusText" compact class="max-sm:hidden" />
        <span class="w-12 shrink-0 text-right font-mono text-[0.6875rem] leading-4 text-fg-3 tabular-nums">{{ durationLabel }}</span>
        <span class="ix-step-track max-sm:hidden" aria-hidden="true">
          <span
            class="ix-step-bar"
            :style="{ width: `${barWidth}%`, backgroundColor: `var(--ix-span-${step.kind})` }"
          />
        </span>
      </summary>

      <div v-if="open" class="ix-step-body">
        <p class="text-[0.6875rem] leading-4 text-fg-3">
          <span class="font-medium text-fg-2">{{ kindLabel }} span</span>
          <span aria-hidden="true"> · </span>
          <span class="font-mono tabular-nums">{{ step.durationMs }} ms</span>
          <span v-if="step.span" aria-hidden="true"> · </span>
          <span v-if="step.span" class="font-mono">starts +{{ step.span.offsetMs }} ms</span>
        </p>

        <div v-if="hasDetails" class="mt-2 grid gap-3 lg:grid-cols-2">
          <SessionJsonBlock label="Arguments" :value="inputValue" :max-lines="12" />
          <SessionJsonBlock label="Output" :value="outputValue" :max-lines="12" />
        </div>
        <p v-else class="mt-2 text-xs leading-4 text-fg-3">No span payload was recorded for this skipped call.</p>

        <div v-if="step.label === 'memory.retrieve' && memories.length" class="mt-3 border-t border-line-subtle pt-3">
          <p class="mb-2 flex items-center gap-1.5 text-[0.6875rem] leading-4 font-medium text-fg-3">
            <Database :size="12" :stroke-width="1.75" aria-hidden="true" />
            Retrieved memories
          </p>
          <ul class="space-y-2.5">
            <li v-for="memory in memories" :key="memory.id" class="min-w-0">
              <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                <NuxtLink
                  v-if="hasMemoryPreview(memory.id)"
                  :to="memoryDetailHref(memory.id, returnTo)"
                  class="min-w-0 truncate text-[0.8125rem] leading-5 font-medium text-fg-1 underline-offset-4 hover:text-accent-memory hover:underline"
                >
                  {{ memory.label }}
                </NuxtLink>
                <span v-else class="min-w-0 truncate text-[0.8125rem] leading-5 font-medium text-fg-1">{{ memory.label }}</span>
                <MemoryOutcomePill
                  :usage="memory.usedInResponse ? 'injected' : 'retrieved_only'"
                  labels="reply"
                  class="ml-auto"
                />
              </div>
              <p class="mt-1 text-xs leading-4 text-fg-2 text-pretty">{{ memory.fact }}</p>
              <div class="mt-1.5 flex items-center gap-2">
                <MemoryScoreBar
                  :value="memory.similarity"
                  size="sm"
                  class="max-w-20"
                  :label="`Retrieval similarity ${memory.similarity.toFixed(2)}`"
                />
                <span class="font-mono text-[0.6875rem] leading-4 text-fg-2 tabular-nums">{{ memory.similarity.toFixed(2) }}</span>
                <span class="text-[0.6875rem] leading-4 text-fg-3">{{ memory.scope }} scope</span>
              </div>
            </li>
          </ul>
        </div>

        <div class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line-subtle pt-2">
          <button
            v-if="canInspect"
            type="button"
            class="inline-flex items-center gap-1 rounded text-[0.6875rem] leading-4 font-medium text-fg-2 transition-colors hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            @click="inspect('trace')"
          >
            Open span in inspector
            <ArrowUpRight :size="11" :stroke-width="1.75" aria-hidden="true" />
          </button>
          <button
            v-else
            type="button"
            class="inline-flex items-center gap-1 rounded text-[0.6875rem] leading-4 font-medium text-fg-3 transition-colors hover:text-fg-1"
            @click="inspect(stepPanel())"
          >
            Open {{ stepPanel() }} tab
            <ArrowUpRight :size="11" :stroke-width="1.75" aria-hidden="true" />
          </button>
          <span
            v-if="step.status !== 'ok'"
            class="text-[0.6875rem] leading-4"
            :class="outcomeTone(step.status === 'error' ? 'error' : 'succeeded') === 'destructive' ? 'text-crit' : 'text-fg-3'"
          >{{ statusText }}</span>
        </div>
      </div>
    </details>
  </li>
</template>

<style scoped>
.ix-step {
  border-radius: 6px;
  transition: background-color 150ms;
}

.ix-step-highlight {
  background: color-mix(in srgb, var(--ix-memory) 9%, transparent);
}

.ix-step-details {
  min-width: 0;
}

.ix-step-row {
  display: grid;
  min-height: 2.25rem;
  cursor: pointer;
  list-style: none;
  align-items: center;
  grid-template-columns: 0.75rem 1rem 10.75rem minmax(0, 1fr) auto auto 2.75rem;
  gap: 0.5rem;
  border-radius: 6px;
  padding: 0 0.375rem;
  transition: background-color 150ms;
}

.ix-step-row::-webkit-details-marker {
  display: none;
}

.ix-step-row:hover {
  background: var(--ix-raised);
}

.ix-step-row:focus-visible {
  outline: 2px solid var(--ix-accent-memory);
  outline-offset: -2px;
}

.ix-step-chevron {
  color: var(--ix-fg-3);
  transition: transform 150ms ease-out;
}

.ix-step-details[open] .ix-step-chevron {
  transform: rotate(90deg);
}

.ix-step-name {
  min-width: 0;
  overflow: hidden;
  border-radius: 3px;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  line-height: 1.25rem;
  color: var(--ix-fg-1);
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ix-step-track {
  width: 2.5rem;
  height: 0.25rem;
  overflow: hidden;
  border-radius: 9999px;
  background: var(--ix-raised);
}

.ix-step-bar {
  display: block;
  height: 100%;
  border-radius: 9999px;
}

.ix-step-body {
  margin: 0 0.375rem 0.375rem 2.75rem;
  border-top: 1px solid var(--ix-line-subtle);
  padding-top: 0.5rem;
}

@media (max-width: 720px) {
  .ix-step-row {
    grid-template-columns: 0.75rem 1rem minmax(0, 1fr) auto auto;
  }

  .ix-step-row > :nth-child(4),
  .ix-step-row > :nth-child(7) {
    display: none;
  }

  .ix-step-name {
    white-space: normal;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ix-step-chevron {
    transition-duration: 1ms;
  }
}
</style>
