<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ArrowRight } from "@lucide/vue"
import type { SessionFocus, SessionRound, SessionSpan } from "@/lib/session-preview"
import {
  criticalSpanIds,
  formatCostShort,
  parseCostUsd,
  slowestSpan,
  spanDepth,
  spanShare,
  spanTotalMs,
  traceEndMs,
  turnToolMs,
  unaccountedMs,
} from "@/lib/session-detail"
import MemoryInfoHint from "@/components/console/memory/primitives/MemoryInfoHint.vue"
import SessionCaveat from "../primitives/SessionCaveat.vue"
import SessionJsonBlock from "../primitives/SessionJsonBlock.vue"
import SessionRawRecord from "../primitives/SessionRawRecord.vue"
import SessionSpanMark from "../primitives/SessionSpanMark.vue"
import SessionStatusPill from "../primitives/SessionStatusPill.vue"
import BrandIcon from "@/components/console/BrandIcon.vue"

const props = defineProps<{
  round: SessionRound
  spanId: string | null
  /** Unique prefix so the inline panel and the sheet never duplicate DOM ids. */
  idPrefix?: string
}>()

const helpId = computed(() => `${props.idPrefix ?? "session"}-trace-help`)

const emit = defineEmits<{
  "update:spanId": [id: string]
  hover: [id: string | null]
  navigate: [panel: SessionFocus]
  transcript: [spanId: string | null]
}>()

const ordered = computed(() =>
  props.round.spans
    .slice()
    .sort((first, second) => first.offsetMs - second.offsetMs || second.durationMs - first.durationMs),
)

const scale = computed(() => Math.max(1, props.round.latencyMs, traceEndMs(props.round)))
const critical = computed(() => criticalSpanIds(props.round.spans))
const totalSpans = computed(() => spanTotalMs(props.round))
const toolMs = computed(() => turnToolMs(props.round))
const gap = computed(() => unaccountedMs(props.round))

const ticks = computed(() => {
  const steps = [10, 20, 25, 50, 80, 100, 160, 200, 250, 500, 800, 1000, 2000, 2500, 5000]
  const target = scale.value / 4
  const step = steps.find((value) => value >= target) ?? Math.ceil(scale.value / 4)
  const end = Math.round(scale.value)
  const values: number[] = []
  for (let value = 0; value < end; value += step) values.push(Math.round(value))
  // Avoid a crowded pair of labels when the final step lands just before the end.
  if (values.length > 0 && end - values[values.length - 1]! < step * 0.45) values.pop()
  values.push(end)
  return values
})

function defaultSpan(): SessionSpan | null {
  const failed = props.round.spans.find((span) => span.status === "error")
  if (failed) return failed
  return slowestSpan(props.round.spans)
}

const selectedId = ref<string | null>(props.spanId ?? defaultSpan()?.id ?? null)

watch(
  () => props.round.id,
  () => {
    const exists = props.round.spans.find((span) => span.id === props.spanId)
    selectedId.value = exists?.id ?? defaultSpan()?.id ?? null
  },
)

watch(
  () => props.spanId,
  (value) => {
    if (value && props.round.spans.some((span) => span.id === value)) selectedId.value = value
  },
)

const selected = computed(() => props.round.spans.find((span) => span.id === selectedId.value) ?? null)

const selectedAttributes = computed(() => selected.value?.attributes ?? {})
const inputValue = computed(() => selectedAttributes.value.input ?? null)
const outputValue = computed(() => selectedAttributes.value.output ?? null)

const presentKinds = computed(() => {
  const order: Array<SessionSpan["kind"]> = ["internal", "retrieval", "tool", "llm", "policy"]
  const present = new Set(props.round.spans.map((span) => span.kind))
  return order.filter((kind) => present.has(kind))
})

const select = (span: SessionSpan): void => {
  selectedId.value = span.id
  emit("update:spanId", span.id)
}

const defaultSelected = (): void => {
  const span = defaultSpan()
  if (span) select(span)
}

function onKeydown(event: KeyboardEvent): void {
  if (props.round.spans.length === 0) return
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return
  event.preventDefault()
  const index = ordered.value.findIndex((span) => span.id === selectedId.value)
  const delta = event.key === "ArrowDown" ? 1 : -1
  const next = ordered.value[Math.min(ordered.value.length - 1, Math.max(0, index + delta))]
  if (next) select(next)
}

if (!selectedId.value) defaultSelected()
</script>

<template>
  <div class="space-y-5">
    <p class="flex flex-wrap items-center gap-x-1.5 text-xs leading-5 text-fg-3">
      <span class="font-mono text-fg-2 tabular-nums">{{ totalSpans }} ms in spans</span>
      <span aria-hidden="true">·</span>
      <span>{{ round.spans.length }} spans</span>
      <span aria-hidden="true">·</span>
      <span class="font-mono tabular-nums">{{ toolMs }} ms in tools</span>
      <MemoryInfoHint label="About illustrative timing">
        Span offsets show execution order in the illustrative record, not measured production latency.
      </MemoryInfoHint>
    </p>

    <section aria-label="Span waterfall">
      <div class="ix-chart" tabindex="0" :aria-describedby="helpId" @keydown="onKeydown">
        <div class="ix-axis" aria-hidden="true">
          <span class="ix-axis-head" />
          <span class="relative block h-4">
            <span
              v-for="tick in ticks"
              :key="tick"
              class="absolute top-0 -translate-x-1/2 font-mono text-[0.5625rem] leading-4 text-fg-3 tabular-nums"
              :style="{ left: `${Math.min(100, (tick / scale) * 100)}%` }"
            >{{ tick }}</span>
          </span>
          <span class="ix-axis-head">ms</span>
        </div>

        <button
          v-for="span in ordered"
          :key="span.id"
          type="button"
          class="ix-row"
          :class="[
            selectedId === span.id && 'ix-row-selected',
            !critical.has(span.id) && selectedId !== span.id && 'ix-row-muted',
          ]"
          :aria-pressed="selectedId === span.id"
          @click="select(span)"
          @mouseenter="emit('hover', span.id)"
          @mouseleave="emit('hover', null)"
        >
          <span class="ix-label" :style="{ paddingLeft: `${spanDepth(round.spans, span) * 12}px` }">
            <SessionSpanMark :kind="span.kind" :size="12" />
            <span class="truncate font-mono text-[0.6875rem] leading-4 text-fg-1" :title="span.label">{{ span.label }}</span>
          </span>
          <span class="ix-track">
            <span
              v-for="tick in ticks"
              :key="`${span.id}-${tick}`"
              class="ix-gridline"
              :style="{ left: `${(tick / scale) * 100}%` }"
              aria-hidden="true"
            />
            <span
              class="ix-bar"
              :class="selectedId === span.id && 'ix-bar-selected'"
              :style="{
                left: `${Math.min(100, (span.offsetMs / scale) * 100)}%`,
                width: `max(3px, ${Math.min(100, (span.durationMs / scale) * 100)}%)`,
                backgroundColor: `var(--ix-span-${span.kind})`,
              }"
            />
          </span>
          <span class="ix-duration font-mono tabular-nums">{{ span.durationMs }} ms</span>
        </button>

        <div v-if="gap > 0" class="ix-row ix-row-gap" aria-label="Unaccounted time">
          <span class="ix-label pl-0 text-[0.6875rem] leading-4 text-fg-3">Unaccounted</span>
          <span class="ix-track">
            <span
              class="ix-gap"
              :style="{
                left: `${Math.min(100, (traceEndMs(round) / scale) * 100)}%`,
                width: `max(3px, ${Math.min(100, (gap / scale) * 100)}%)`,
              }"
            />
            <span class="ix-gap-label">Unaccounted · {{ gap }} ms</span>
          </span>
          <span class="ix-duration font-mono tabular-nums text-fg-3">{{ gap }} ms</span>
        </div>
      </div>

      <p :id="helpId" class="sr-only">
        Use the up and down arrow keys to move through spans. The selected span is described below the chart.
      </p>

      <div class="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1.5" aria-label="Span kinds">
        <span v-for="kind in presentKinds" :key="kind" class="inline-flex items-center gap-1.5 text-[0.6875rem] leading-4 text-fg-3">
          <span class="size-2 rounded-[2px]" :style="{ backgroundColor: `var(--ix-span-${kind})` }" aria-hidden="true" />
          {{ kind === "llm" ? "LLM" : kind.charAt(0).toUpperCase() + kind.slice(1) }}
        </span>
      </div>

      <table class="sr-only">
        <caption>Span timings for turn {{ round.index }}</caption>
        <thead>
          <tr><th scope="col">Span</th><th scope="col">Start</th><th scope="col">Duration</th><th scope="col">Status</th></tr>
        </thead>
        <tbody>
          <tr v-for="span in ordered" :key="`a11y-${span.id}`">
            <th scope="row">{{ span.label }}</th>
            <td>+{{ span.offsetMs }} ms</td>
            <td>{{ span.durationMs }} ms</td>
            <td>{{ span.status === "ok" ? "ok" : "failed" }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="selected" class="ix-detail" aria-label="Selected span">
      <div class="flex items-baseline justify-between gap-2">
        <p class="min-w-0 truncate font-mono text-xs leading-4 text-fg-1">{{ selected.label }}</p>
        <span class="shrink-0 font-mono text-[0.6875rem] leading-4 text-fg-3 tabular-nums">
          {{ selected.durationMs }} ms · {{ spanShare(selected, Math.max(1, round.latencyMs)) }}%
        </span>
      </div>

      <p v-if="selected.status === 'error'" class="mt-2 flex items-start gap-1.5 text-xs leading-4 text-crit">
        <span aria-hidden="true">✕</span>
        <span>{{ selected.summary }}</span>
      </p>

      <dl class="mt-2 grid grid-cols-[6rem_minmax(0,1fr)] items-baseline gap-x-3 gap-y-1 text-[0.8125rem] leading-5">
        <dt class="text-fg-3">Kind</dt>
        <dd class="text-fg-1">{{ selected.kind === "llm" ? "LLM" : selected.kind.charAt(0).toUpperCase() + selected.kind.slice(1) }}</dd>
        <dt class="text-fg-3">Start</dt>
        <dd class="font-mono text-xs text-fg-1 tabular-nums">+{{ selected.offsetMs }} ms</dd>
        <dt class="text-fg-3">Status</dt>
        <dd>
          <SessionStatusPill :tone="selected.status === 'ok' ? 'success' : 'destructive'" :label="selected.status === 'ok' ? 'ok' : 'failed'" compact />
        </dd>
        <template v-if="selected.kind === 'llm'">
          <dt class="text-fg-3">Model</dt>
          <dd class="inline-flex items-center gap-1.5 text-fg-1"><BrandIcon :id="round.model" :size="12" :label="`${round.model} logo`" />{{ round.model }}</dd>
          <dt class="text-fg-3">Tokens</dt>
          <dd class="font-mono text-xs text-fg-1 tabular-nums">{{ round.tokensIn }} in · {{ round.tokensOut }} out</dd>
          <dt class="text-fg-3">Cost</dt>
          <dd class="font-mono text-xs text-fg-1 tabular-nums">{{ formatCostShort(parseCostUsd(round.cost)) }}</dd>
        </template>
        <template v-else-if="selected.kind === 'tool'">
          <dt class="text-fg-3">Tool</dt>
          <dd class="font-mono text-xs text-fg-1">{{ selected.label.replace(/^tool\./, "") }}</dd>
        </template>
        <template v-else-if="selected.kind === 'retrieval'">
          <dt class="text-fg-3">Memories</dt>
          <dd class="text-fg-1">
            {{ round.memories.length }} returned · {{ round.memories.filter((memory) => memory.usedInResponse).length }} included
            <button type="button" class="ix-inline-link" @click="emit('navigate', 'memories')">View memories</button>
          </dd>
        </template>
        <template v-else-if="selected.kind === 'policy'">
          <dt class="text-fg-3">Decision</dt>
          <dd class="text-fg-1">
            {{ round.policy.decision === "allow" ? "Allowed" : round.policy.decision === "deny" ? "Blocked" : "Needs approval" }}
            <button type="button" class="ix-inline-link" @click="emit('navigate', 'policy')">View policy</button>
          </dd>
        </template>
      </dl>

      <div v-if="inputValue || outputValue" class="mt-3 grid gap-3">
        <SessionJsonBlock v-if="inputValue" label="Input" :value="inputValue" :max-lines="8" />
        <SessionJsonBlock v-if="outputValue" label="Output" :value="outputValue" :max-lines="8" />
      </div>

      <button type="button" class="ix-inline-link mt-3" @click="emit('transcript', selectedId)">
        Show in transcript
        <ArrowRight :size="11" :stroke-width="1.75" aria-hidden="true" />
      </button>
    </section>

    <SessionCaveat
      summary="Timing is illustrative."
      detail="Span offsets show execution order, not measured production latency. Every total above is computed from the spans shown."
    />

    <SessionRawRecord :value="round" />
  </div>
</template>

<style scoped>
.ix-chart {
  border-radius: 8px;
  outline: none;
}

.ix-chart:focus-visible {
  outline: 2px solid var(--ix-accent-memory);
  outline-offset: 2px;
}

.ix-axis,
.ix-row {
  display: grid;
  grid-template-columns: 13.5rem minmax(0, 1fr) 3.25rem;
  align-items: center;
  gap: 0.5rem;
}

.ix-axis {
  margin-bottom: 0.125rem;
}

.ix-axis-head {
  font-family: var(--font-mono);
  font-size: 0.5625rem;
  line-height: 1rem;
  color: var(--ix-fg-3);
  text-align: right;
}

.ix-row {
  width: 100%;
  min-height: 1.75rem;
  border-radius: 5px;
  padding: 0.125rem 0.25rem;
  text-align: left;
  transition: background-color 120ms;
}

.ix-row:hover {
  background: var(--ix-raised);
}

.ix-row-selected {
  background: var(--ix-surface-2);
}

.ix-row:focus-visible {
  outline: 2px solid var(--ix-accent-memory);
  outline-offset: -2px;
}

.ix-label {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0.375rem;
  overflow: hidden;
}

.ix-track {
  position: relative;
  display: block;
  height: 0.5rem;
}

.ix-gridline {
  position: absolute;
  top: -0.625rem;
  bottom: -0.625rem;
  width: 1px;
  background: color-mix(in srgb, var(--ix-line-subtle) 75%, transparent);
  pointer-events: none;
}

.ix-bar {
  position: absolute;
  top: 0;
  height: 0.5rem;
  border-radius: 2px;
  transition: width 250ms ease-out;
}

.ix-bar-selected {
  box-shadow: 0 0 0 1.5px var(--ix-canvas), 0 0 0 2.5px var(--ix-fg-2);
}

.ix-duration {
  font-size: 0.6875rem;
  line-height: 1rem;
  color: var(--ix-fg-2);
  text-align: right;
  white-space: nowrap;
}

.ix-row-gap {
  min-height: 1.5rem;
}

/* Mute the bar, never the label: text must keep its contrast on the surface. */
.ix-row-muted .ix-bar {
  opacity: 0.55;
}

.ix-gap {
  position: absolute;
  top: 0.1875rem;
  height: 0.125rem;
  border-top: 1px dashed var(--ix-line-strong);
}

.ix-gap-label {
  position: absolute;
  top: -0.0625rem;
  left: 50%;
  font-size: 0.5625rem;
  line-height: 1;
  color: var(--ix-fg-3);
  transform: translateX(-50%);
  white-space: nowrap;
}

.ix-detail {
  border: 1px solid var(--ix-line);
  border-radius: 10px;
  background: var(--ix-surface);
  padding: 0.75rem 0.875rem;
}

.ix-inline-link {
  display: inline-flex;
  align-items: center;
  gap: 0.1875rem;
  border-radius: 3px;
  font-size: 0.6875rem;
  line-height: 1rem;
  font-weight: 500;
  color: var(--ix-fg-2);
  text-decoration: underline;
  text-decoration-color: var(--ix-line-strong);
  text-underline-offset: 2px;
  transition: color 120ms;
}

.ix-inline-link:hover {
  color: var(--ix-fg-1);
}

.ix-inline-link:focus-visible {
  outline: 2px solid var(--ix-accent-memory);
  outline-offset: 2px;
}

@media (max-width: 480px) {
  .ix-axis,
  .ix-row {
    grid-template-columns: 9rem minmax(0, 1fr) 3rem;
    gap: 0.375rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ix-bar {
    transition-duration: 1ms;
  }
}
</style>