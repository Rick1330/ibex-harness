<script setup lang="ts">
import { computed } from "vue"
import type { PublicOperatorTraceDetail } from "~~/shared/operator/public"
import { GitBranch, List, Map as MapIcon, Waves } from "@lucide/vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernPendingData from "@/components/console/govern/primitives/GovernPendingData.vue"
import { EXPLORE_LENS_LABELS, EXPLORE_LENS_MEANING, type ExploreLens } from "@/lib/govern-query"
import { formatDuration } from "@/lib/format"
import { formatGovernNumber, formatGovernStampMillis } from "@/lib/govern-format"
import { EXPLORE_TRACE_DETAIL_CONTRACT } from "@/lib/explore-view"

const props = defineProps<{
  detail: PublicOperatorTraceDetail
  lens: ExploreLens
}>()

const emit = defineEmits<{ "update:lens": [lens: ExploreLens] }>()

type Span = PublicOperatorTraceDetail["spans"][number]

const lenses: Array<{ id: ExploreLens; icon: typeof Waves }> = [
  { id: "waterfall", icon: Waves },
  { id: "tree", icon: GitBranch },
  { id: "list", icon: List },
  { id: "map", icon: MapIcon },
]

const spans = computed<Span[]>(() => props.detail.spans)

/** `spans` is a declared section, so an empty array is only meaningful when it is not marked unavailable. */
const spansAvailable = computed(() => !isUnavailable("spans") && spans.value.length > 0)

function isUnavailable(section: string): boolean {
  return props.detail.unavailable_sections.some((entry) => entry === section)
}

const startMs = computed(() => {
  const parsed = Date.parse(props.detail.started_at)
  return Number.isFinite(parsed) ? parsed : 0
})

/** The axis runs from the recorded start to the latest recorded end. Nothing is extrapolated. */
const axisMs = computed(() => {
  const ends = spans.value
    .map((span) => (span.ended_at ? Date.parse(span.ended_at) : null))
    .filter((value): value is number => value !== null && Number.isFinite(value))
  if (props.detail.ended_at) {
    const runEnd = Date.parse(props.detail.ended_at)
    if (Number.isFinite(runEnd)) ends.push(runEnd)
  }
  const end = ends.length ? Math.max(...ends) : startMs.value
  return Math.max(1, end - startMs.value)
})

const orderedSpans = computed(() =>
  [...spans.value].sort((left, right) => {
    const delta = Date.parse(left.started_at) - Date.parse(right.started_at)
    return delta === 0 ? left.span_id.localeCompare(right.span_id) : delta
  }),
)

const spanDepths = computed(() => {
  const byId = new Map(spans.value.map((span) => [span.span_id, span]))
  const cache = new Map<string, number>()
  function depth(spanId: string, seen: Set<string>): number {
    const cached = cache.get(spanId)
    if (cached !== undefined) return cached
    const span = byId.get(spanId)
    if (!span?.parent_span_id || seen.has(spanId) || seen.size > 32) return 0
    seen.add(spanId)
    const value = 1 + depth(span.parent_span_id, seen)
    cache.set(spanId, value)
    return value
  }
  const depths = new Map<string, number>()
  for (const span of spans.value) depths.set(span.span_id, depth(span.span_id, new Set()))
  return depths
})

const openSpanCount = computed(() => spans.value.filter((span) => span.ended_at === null).length)
const errorSpanCount = computed(() => spans.value.filter((span) => span.status !== "ok").length)

function offsetPercent(span: Span): number {
  const started = Date.parse(span.started_at)
  if (!Number.isFinite(started)) return 0
  return Math.max(0, Math.min(100, ((started - startMs.value) / axisMs.value) * 100))
}

/** `null` means the span never recorded an end — it is drawn open, not as a zero-width bar. */
function widthPercent(span: Span): number | null {
  if (span.ended_at === null) return null
  const started = Date.parse(span.started_at)
  const ended = Date.parse(span.ended_at)
  if (!Number.isFinite(started) || !Number.isFinite(ended) || ended < started) return null
  return Math.max(0.6, Math.min(100 - offsetPercent(span), ((ended - started) / axisMs.value) * 100))
}

function spanDuration(span: Span): string {
  if (span.ended_at === null) return "Open"
  const started = Date.parse(span.started_at)
  const ended = Date.parse(span.ended_at)
  if (!Number.isFinite(started) || !Number.isFinite(ended) || ended < started) return "Not recorded"
  return formatDuration(ended - started)
}

function spanTitle(span: Span): string {
  const status = span.status === "ok" ? "Reported no error" : `Status ${span.status}`
  const error = span.error_code ? ` · ${span.error_code}` : ""
  return `${status}${error} · started ${formatGovernStampMillis(span.started_at)}`
}

const openBarStyle = {
  backgroundImage:
    "repeating-linear-gradient(135deg, color-mix(in srgb, var(--ix-accent) 34%, transparent) 0 3px, transparent 3px 6px)",
} as const
</script>

<template>
  <section class="flex min-w-0 flex-col gap-2" aria-label="Span timeline">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="flex flex-wrap items-center gap-0.5 rounded-lg border border-line-subtle bg-surface p-0.5" role="group" aria-label="Span lens">
        <button
          v-for="option in lenses"
          :key="option.id"
          type="button"
          class="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
          :class="props.lens === option.id ? 'bg-raised text-fg-1' : 'text-fg-3 hover:text-fg-1'"
          :aria-pressed="props.lens === option.id"
          :title="EXPLORE_LENS_MEANING[option.id]"
          @click="emit('update:lens', option.id)"
        >
          <component :is="option.icon" :size="13" :stroke-width="1.8" aria-hidden="true" />
          {{ EXPLORE_LENS_LABELS[option.id] }}
        </button>
      </div>
      <p class="font-mono text-[0.6875rem] leading-4 text-fg-3">
        {{ formatGovernNumber(spans.length) }} span{{ spans.length === 1 ? "" : "s" }}
        <span v-if="openSpanCount"> · {{ openSpanCount }} open</span>
        <span v-if="errorSpanCount"> · {{ errorSpanCount }} not ok</span>
      </p>
    </div>

    <div v-if="!spansAvailable" class="min-w-0">
      <GovernPendingData
        title="Span timings"
        :contract="EXPLORE_TRACE_DETAIL_CONTRACT"
        :description="isUnavailable('spans')
          ? 'The contract marks spans unavailable for this run. A flat timeline would look like a fast run, so none is drawn.'
          : 'The run returned no span rows. Absence is reported as recorded rather than as a single unnamed operation.'"
      />
    </div>

    <template v-else>
      <!-- Waterfall -->
      <div v-if="props.lens === 'waterfall'" class="min-w-0 overflow-hidden rounded-lg border border-line-subtle bg-surface">
        <div class="flex items-center justify-between border-b border-line-subtle px-3 py-2">
          <p class="text-xs font-medium text-fg-1">Position on the run's own axis</p>
          <p class="font-mono text-[0.6875rem] leading-4 text-fg-3">{{ formatDuration(axisMs) }} observed</p>
        </div>
        <div class="ix-scroll overflow-x-auto" aria-label="Span waterfall">
          <div class="flex flex-col" style="min-width: 640px">
            <div
              v-for="span in orderedSpans"
              :key="span.span_id"
              class="flex items-center gap-2 border-b border-line-subtle px-3 py-1.5 last:border-0"
            >
              <span class="shrink-0 truncate font-mono text-xs leading-5 text-fg-1" style="width: 190px" :title="`${span.operation_kind} · ${span.span_id}`">
                {{ span.operation_kind }}
              </span>
              <span class="relative h-4 min-w-0 flex-1 rounded-sm bg-raised">
                <span
                  v-if="widthPercent(span) !== null"
                  class="absolute inset-y-0 rounded-sm"
                  :class="span.status === 'ok' ? 'bg-accent/35' : 'bg-crit/35'"
                  :style="{ left: `${offsetPercent(span)}%`, width: `${widthPercent(span)}%` }"
                />
                <span
                  v-else
                  class="absolute inset-y-0 rounded-sm border-r border-dashed border-accent/70"
                  :style="{ ...openBarStyle, left: `${offsetPercent(span)}%`, width: `${100 - offsetPercent(span)}%` }"
                />
              </span>
              <span
                class="shrink-0 text-right font-mono text-xs leading-5 tabular-nums"
                style="width: 108px"
                :class="span.status === 'ok' ? 'text-fg-3' : 'text-crit'"
                :title="spanTitle(span)"
              >
                {{ spanDuration(span) }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Tree -->
      <div v-else-if="props.lens === 'tree'" class="min-w-0 overflow-hidden rounded-lg border border-line-subtle bg-surface">
        <p class="border-b border-line-subtle px-3 py-2 text-xs font-medium text-fg-1">Nested by the parent each span reports</p>
        <ul class="ix-scroll overflow-x-auto" aria-label="Span tree">
          <li
            v-for="span in spans"
            :key="span.span_id"
            class="flex items-center gap-2 border-b border-line-subtle px-3 py-1.5 text-xs last:border-0"
            :style="{ paddingLeft: `${0.75 + Math.min(spanDepths.get(span.span_id) ?? 0, 8) * 0.875}rem` }"
          >
            <span class="size-1.5 shrink-0 rounded-full" :class="span.status === 'ok' ? 'bg-ok' : 'bg-crit'" aria-hidden="true" />
            <span class="min-w-0 truncate font-mono leading-5 text-fg-1" :title="span.span_id">{{ span.operation_kind }}</span>
            <span v-if="span.error_code" class="shrink-0 truncate font-mono text-[0.6875rem] leading-4 text-crit" :title="span.error_code">
              {{ span.error_code }}
            </span>
            <span class="ml-auto shrink-0 font-mono text-[0.6875rem] leading-4 text-fg-3 tabular-nums">{{ spanDuration(span) }}</span>
          </li>
        </ul>
      </div>

      <!-- List -->
      <div v-else-if="props.lens === 'list'" class="min-w-0 ix-scroll overflow-x-auto rounded-lg border border-line-subtle">
        <table class="ix-agent-table" style="min-width: 760px" aria-label="Span list">
          <thead>
            <tr>
              <th scope="col">Span id</th>
              <th scope="col">Parent</th>
              <th scope="col">Operation</th>
              <th scope="col">Status</th>
              <th scope="col">Started</th>
              <th scope="col" class="text-right">Duration</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="span in spans" :key="span.span_id">
              <td class="truncate font-mono text-xs" :title="span.span_id">{{ span.span_id }}</td>
              <td class="truncate font-mono text-xs text-fg-3" :title="span.parent_span_id ?? ''">{{ span.parent_span_id ?? "Root" }}</td>
              <td class="truncate font-mono text-xs text-fg-1">{{ span.operation_kind }}</td>
              <td class="font-mono text-xs" :class="span.status === 'ok' ? 'text-fg-2' : 'text-crit'">
                {{ span.status }}
                <span v-if="span.error_code" class="block truncate text-[0.6875rem] leading-4 text-crit" :title="span.error_code">{{ span.error_code }}</span>
              </td>
              <td class="whitespace-nowrap font-mono text-xs text-fg-2" :title="formatGovernStampMillis(span.started_at)">
                {{ formatGovernStampMillis(span.started_at) }}
              </td>
              <td class="whitespace-nowrap text-right font-mono text-xs text-fg-2 tabular-nums">{{ spanDuration(span) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Map -->
      <div v-else class="grid min-w-0 gap-2 sm:grid-cols-2">
        <div v-for="span in spans" :key="span.span_id" class="min-w-0 rounded-lg border border-line-subtle bg-surface p-3">
          <div class="flex items-baseline justify-between gap-2">
            <p class="min-w-0 truncate font-mono text-xs leading-5 text-fg-1" :title="span.operation_kind">{{ span.operation_kind }}</p>
            <p class="shrink-0 font-mono text-[0.6875rem] leading-4" :class="span.status === 'ok' ? 'text-fg-3' : 'text-crit'">
              {{ span.status }}
            </p>
          </div>
          <dl class="mt-1.5 flex flex-col gap-1 font-mono text-[0.6875rem] leading-4 text-fg-3">
            <div class="flex items-baseline justify-between gap-2">
              <dt>span</dt>
              <dd class="min-w-0 truncate text-fg-2" :title="span.span_id">{{ span.span_id }}</dd>
            </div>
            <div class="flex items-baseline justify-between gap-2">
              <dt>parent</dt>
              <dd class="min-w-0 truncate text-fg-2" :title="span.parent_span_id ?? ''">{{ span.parent_span_id ?? "Root" }}</dd>
            </div>
            <div class="flex items-baseline justify-between gap-2">
              <dt>started</dt>
              <dd class="min-w-0 truncate text-fg-2" :title="formatGovernStampMillis(span.started_at)">{{ formatGovernStampMillis(span.started_at) }}</dd>
            </div>
            <div class="flex items-baseline justify-between gap-2">
              <dt>ended</dt>
              <dd class="min-w-0 truncate text-fg-2" :title="formatGovernStampMillis(span.ended_at)">{{ formatGovernStampMillis(span.ended_at) }}</dd>
            </div>
            <div class="flex items-baseline justify-between gap-2">
              <dt>duration</dt>
              <dd class="min-w-0 truncate text-fg-1">{{ spanDuration(span) }}</dd>
            </div>
          </dl>
        </div>
      </div>

      <GovernCaveat tone="info" title="How to read this">
        Every bar is a span the contract returned, positioned on the axis the run itself defines. A hatched bar that runs
        to the right edge is a span with no recorded end — it is open, not slow. Prompt and completion text never appear
        here: that is a standing rule of the contract, not a retention outcome for this run.
      </GovernCaveat>
    </template>
  </section>
</template>
