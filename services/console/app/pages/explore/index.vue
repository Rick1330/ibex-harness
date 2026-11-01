<script setup lang="ts">
import { computed, ref } from "vue"
import type { PublicOperatorTrace } from "~~/shared/operator/public"
import { ArrowRight, ChevronRight } from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernFilterBar from "@/components/console/govern/primitives/GovernFilterBar.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import GovernPeekSheet from "@/components/console/govern/primitives/GovernPeekSheet.vue"
import GovernShortcutsDialog from "@/components/console/govern/primitives/GovernShortcutsDialog.vue"
import IxTierMark from "@/components/console/IxTierMark.vue"
import { useGovernShortcuts } from "@/composables/useGovernShortcuts"
import { useConsoleDemo } from "@/composables/useConsoleDemo"
import { useTriageTable } from "@/composables/useTriageTable"
import { formatDuration, shortenId } from "@/lib/format"
import { DEMO_TRACE_LIST } from "@/lib/console-demo"
import { formatGovernNumber, formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"
import { tierForTrace } from "@/lib/certification"
import {
  BROKEN_PUBLICATION,
  COMPLETENESS_LABELS,
  COMPLETENESS_MEANING,
  EXPLORE_QUERY_GRAMMAR,
  EXPLORE_LIST_NOTES,
  EXPLORE_TRACE_LIST_CONTRACT,
  FRESHNESS_LABELS,
  FRESHNESS_MEANING,
  PUBLICATION_LABELS,
  PUBLICATION_MEANING,
  RETENTION_LABELS,
  RETENTION_MEANING,
  TRACE_STATUS_LABELS,
  TRACE_STATUS_MEANING,
  completenessClass,
  exploreAttention,
  freshnessClass,
  publicationClass,
  type TraceCompleteness,
} from "@/lib/explore-view"
import {
  LiveExploreQueryError,
  parseLiveExploreQuery,
  serializeLiveExploreQuery,
  type LiveExploreQuery,
} from "~~/shared/operator/explore-query"

definePageMeta({
  key: (route) => route.fullPath,
})

useHead({ title: "Explore · IBEX Console" })

const route = useRoute()

/* ------------------------------------------------------------------ query */

let parsed: LiveExploreQuery | null = null
let urlError: string | null = null
try {
  parsed = parseLiveExploreQuery(route.query)
} catch (error) {
  urlError = error instanceof LiveExploreQueryError ? error.message : "Invalid Explore query"
}

const params = computed(() => (parsed ? serializeLiveExploreQuery(parsed) : new URLSearchParams()))
const tracesState = useTraceList(params.value, Boolean(parsed))
const demo = useConsoleDemo()
const demoActive = computed(() => demo.value && Boolean(parsed) && !tracesState.data.value)
const traces = computed(() => tracesState.data.value ?? (demoActive.value ? DEMO_TRACE_LIST : null))
const items = computed(() => traces.value?.items ?? [])

const outcomeSegments = computed(() => {
  const ok = items.value.filter((trace) => trace.status === "ok").length
  return [
    { label: "OK", value: ok, color: "bg-s1" },
    { label: "Failed", value: items.value.length - ok, color: "bg-crit" },
  ]
})

const completenessSegments = computed(() => {
  const counts = new Map<string, number>()
  for (const trace of items.value) {
    counts.set(trace.evidence.completeness, (counts.get(trace.evidence.completeness) ?? 0) + 1)
  }
  const colors: Record<string, string> = {
    complete: "bg-s1",
    partial: "bg-warn",
    sampled: "bg-s3",
    late: "bg-s2",
    redacted: "bg-fg-3",
    expired: "bg-fg-off",
    deleted: "bg-crit",
    simulated: "bg-s5",
  }
  return [...counts.entries()].map(([label, value]) => ({
    label: COMPLETENESS_LABELS[label as keyof typeof COMPLETENESS_LABELS] ?? label,
    value,
    color: colors[label] ?? "bg-fg-3",
  }))
})

const queryInput = ref(parsed ? queryText(parsed) : "")
const queryError = ref<string | null>(urlError)
const search = ref<InstanceType<typeof GovernFilterBar> | null>(null)

const errorStatus = computed(() => {
  const status = (tracesState.error.value as { statusCode?: number } | null)?.statusCode
  return status ?? null
})
const authIssue = computed(() => !demoActive.value && (errorStatus.value === 401 || errorStatus.value === 403))
const tracesFailed = computed(() => !demoActive.value && Boolean(tracesState.error.value))

const listHref = computed(() => `/explore${params.value.toString() ? `?${params.value.toString()}` : ""}`)
const firstHref = computed(() => {
  if (!parsed) return "/explore"
  return `/explore?${serializeLiveExploreQuery(parsed, { dropCursor: true }).toString()}`
})
const nextHref = computed(() => {
  if (!parsed || !traces.value?.next_cursor || !traces.value.truncated) return null
  return `/explore?${serializeLiveExploreQuery({ ...parsed, cursor: traces.value.next_cursor }).toString()}`
})

const completenessOptions = [
  "complete",
  "partial",
  "sampled",
  "late",
  "redacted",
  "expired",
  "deleted",
  "simulated",
] as const

const shorthands: Record<string, keyof LiveExploreQuery> = {
  trace: "trace_id",
  run: "run_id",
  session: "session_id",
}

const allowedKeys = new Set<keyof LiveExploreQuery>([
  "limit",
  "status",
  "started_after",
  "started_before",
  "cursor",
  "trace_id",
  "request_id",
  "run_id",
  "session_id",
  "error_code",
  "completeness",
  "capture_mode",
])

function queryText(query: LiveExploreQuery): string {
  const parts: string[] = []
  if (query.status) parts.push(`status:${query.status}`)
  if (query.completeness) parts.push(`completeness:${query.completeness}`)
  if (query.trace_id) parts.push(`trace:${query.trace_id}`)
  if (query.run_id) parts.push(`run:${query.run_id}`)
  if (query.session_id) parts.push(`session:${query.session_id}`)
  if (query.request_id) parts.push(`request_id:${query.request_id}`)
  if (query.error_code) parts.push(`error_code:${query.error_code}`)
  if (query.capture_mode) parts.push(`capture_mode:${query.capture_mode}`)
  if (query.started_after) parts.push(`started_after:${query.started_after}`)
  if (query.started_before) parts.push(`started_before:${query.started_before}`)
  if (query.limit !== 50) parts.push(`limit:${query.limit}`)
  return parts.join(" ")
}

function parseQueryText(text: string): LiveExploreQuery {
  const raw: Record<string, string> = {}
  const tokens = text.trim().split(/\s+/).filter(Boolean)
  for (const token of tokens) {
    const separator = token.indexOf(":")
    if (separator <= 0) {
      throw new LiveExploreQueryError(`Expected field:value, received "${token}"`)
    }
    const rawKey = token.slice(0, separator)
    const value = token.slice(separator + 1)
    const key = shorthands[rawKey] ?? (rawKey as keyof LiveExploreQuery)
    if (!allowedKeys.has(key)) {
      throw new LiveExploreQueryError(`Unknown query field: ${rawKey}`)
    }
    raw[key] = value
  }
  return parseLiveExploreQuery(raw)
}

function applyQuery(): void {
  try {
    const next = parseQueryText(queryInput.value)
    queryError.value = null
    void navigateTo(`/explore?${serializeLiveExploreQuery(next).toString()}`)
  } catch (error) {
    queryError.value = error instanceof Error ? error.message : "Invalid Explore query"
  }
}

/** Selects and chips write the same URL the query box writes, so both stay in sync. */
function go(patch: Partial<LiveExploreQuery>): void {
  if (!parsed) return
  void navigateTo(`/explore?${serializeLiveExploreQuery({ ...parsed, ...patch, cursor: null }).toString()}`)
}

function clearFilters(): void {
  go({
    status: null,
    completeness: null,
    error_code: null,
    capture_mode: null,
    trace_id: null,
    run_id: null,
    session_id: null,
    request_id: null,
    started_after: null,
    started_before: null,
  })
}

function detailHref(kind: "t" | "r", id: string): string {
  return `/explore/${kind}/${encodeURIComponent(id)}?return=${encodeURIComponent(listHref.value)}`
}

/* ------------------------------------------------------------------ chips */

const savedViews: Array<{ label: string; patch: Partial<LiveExploreQuery>; hint: string }> = [
  { label: "All runs", patch: { status: null, completeness: null, error_code: null }, hint: "No status or completeness filter." },
  { label: "Failed", patch: { status: "error", completeness: null }, hint: "status:error" },
  { label: "Incomplete records", patch: { status: null, completeness: "partial" }, hint: "completeness:partial" },
  { label: "Deleted content", patch: { status: null, completeness: "deleted" }, hint: "completeness:deleted" },
  { label: "Latest 25", patch: { status: null, completeness: null, limit: 25 }, hint: "limit:25" },
]

function viewActive(patch: Partial<LiveExploreQuery>): boolean {
  if (!parsed) return false
  const next = { ...parsed, ...patch, cursor: null }
  return serializeLiveExploreQuery(next).toString() === params.value.toString()
}

/** Counts describe this page only. The list contract has no corpus-wide aggregate, so none is implied. */
const pageCounts = computed(() => {
  const counts = new Map<string, number>()
  for (const trace of items.value) {
    const key = `completeness:${trace.evidence.completeness}`
    counts.set(key, (counts.get(key) ?? 0) + 1)
    if (BROKEN_PUBLICATION.includes(trace.evidence.publication_state)) {
      const pub = `publication:${trace.evidence.publication_state}`
      counts.set(pub, (counts.get(pub) ?? 0) + 1)
    }
  }
  return counts
})

const attention = computed(() => exploreAttention(items.value))

const statusOptions = [
  { value: "all", label: "Any status" },
  { value: "ok", label: TRACE_STATUS_LABELS.ok },
  { value: "error", label: TRACE_STATUS_LABELS.error },
]

const completenessSelectOptions = [
  { value: "all", label: "Any completeness" },
  ...completenessOptions.map((value) => ({ value, label: COMPLETENESS_LABELS[value] })),
]

const limitOptions = [25, 50, 100].map((value) => ({ value: String(value), label: `${value} rows` }))

const activeFilterCount = computed(() => {
  if (!parsed) return 0
  return [
    parsed.status !== null,
    parsed.completeness !== null,
    parsed.error_code !== null,
    parsed.capture_mode !== null,
    parsed.trace_id !== null,
    parsed.run_id !== null,
    parsed.session_id !== null,
    parsed.request_id !== null,
    parsed.started_after !== null,
    parsed.started_before !== null,
  ].filter(Boolean).length
})

const resultText = computed(() => {
  if (!traces.value) return ""
  const returned = formatGovernNumber(traces.value.returned_count)
  const matched = traces.value.matched_count === null ? null : formatGovernNumber(traces.value.matched_count)
  const plus = traces.value.truncated ? "+" : ""
  return matched === null
    ? `${returned} runs on this page`
    : `${returned}${plus} of ${matched} matched runs`
})

const headerState = computed<"live" | "partial" | "illustrative">(() => (demoActive.value ? "illustrative" : traces.value && !tracesState.error.value ? "live" : "partial"))

/* --------------------------------------------------------------- triage */

type TraceRow = { id: string; trace: PublicOperatorTrace }

const triageRows = computed<TraceRow[]>(() => items.value.map((trace) => ({ id: trace.run_id, trace })))

const peekOpen = ref(false)
const peekId = ref<string | null>(null)
const peekRow = computed(() => triageRows.value.find((row) => row.id === peekId.value) ?? null)

const triage = useTriageTable({
  rows: triageRows,
  enabled: () => !peekOpen.value,
  onOpen: (row) => void navigateTo(detailHref("r", row.trace.run_id)),
  onPeek: (row) => {
    peekId.value = row.id
    peekOpen.value = true
  },
})

function peek(trace: PublicOperatorTrace): void {
  peekId.value = trace.run_id
  peekOpen.value = true
}

function copyCurrentLink(): void {
  if (!import.meta.client) return
  void navigator.clipboard.writeText(`${window.location.origin}${listHref.value}`)
}

const { helpOpen } = useGovernShortcuts({
  onSearch: () => search.value?.focus(),
  onEscape: () => {
    if (peekOpen.value) {
      peekOpen.value = false
      return
    }
    triage.select(null)
  },
  keys: { y: copyCurrentLink },
})

const shortcutGroups = [
  {
    title: "This page",
    rows: [
      { keys: "/", label: "Focus the query box" },
      { keys: "j / k", label: "Move between runs" },
      { keys: "Enter", label: "Open the run detail" },
      { keys: "Space", label: "Peek without leaving the list" },
      { keys: "y", label: "Copy link to this exact query" },
      { keys: "g e", label: "Go to evidence" },
      { keys: "g a", label: "Go to audit log" },
      { keys: "?", label: "Show this sheet" },
    ],
  },
]

/* ---------------------------------------------------------------- peek */

type PeekFact = { label: string; value: string; meaning: string; class: string }

const peekFacts = computed<PeekFact[]>(() => {
  const trace = peekRow.value?.trace
  if (!trace) return []
  const evidence = trace.evidence
  return [
    { label: "Status", value: TRACE_STATUS_LABELS[trace.status], meaning: TRACE_STATUS_MEANING[trace.status], class: trace.status === "error" ? "text-crit" : "text-fg-1" },
    {
      label: "Completeness",
      value: COMPLETENESS_LABELS[evidence.completeness],
      meaning: COMPLETENESS_MEANING[evidence.completeness],
      class: completenessClass(evidence.completeness),
    },
    {
      label: "Publication",
      value: PUBLICATION_LABELS[evidence.publication_state],
      meaning: PUBLICATION_MEANING[evidence.publication_state],
      class: publicationClass(evidence.publication_state),
    },
    { label: "Freshness", value: FRESHNESS_LABELS[evidence.freshness], meaning: FRESHNESS_MEANING[evidence.freshness], class: freshnessClass(evidence.freshness) },
    { label: "Retention", value: RETENTION_LABELS[evidence.retention], meaning: RETENTION_MEANING[evidence.retention], class: "text-fg-1" },
    {
      label: "Source watermark",
      value: evidence.source_watermark === "not_provided" ? "Not recorded" : evidence.source_watermark,
      meaning: "The outbox sequence this evidence row was written at, when the source reported one.",
      class: "text-fg-1",
    },
    {
      label: "Ingestion lag",
      value: evidence.ingestion_lag_ms === null ? "Not recorded" : formatDuration(evidence.ingestion_lag_ms),
      meaning: "Delay between the run and the evidence row becoming readable.",
      class: "text-fg-1",
    },
    { label: "Capture mode", value: evidence.capture_mode, meaning: "Which capture path produced this record.", class: "text-fg-1" },
    { label: "Started", value: formatGovernStamp(trace.started_at), meaning: "When the run began.", class: "text-fg-1" },
    {
      label: "Ended",
      value: trace.ended_at === null ? "Not recorded" : formatGovernStamp(trace.ended_at),
      meaning: "When the run finished. Absent means the end was never written.",
      class: "text-fg-1",
    },
    {
      label: "Duration",
      value: trace.duration_ms === null ? "Not recorded" : formatDuration(trace.duration_ms),
      meaning: "Reported by the proxy for this run.",
      class: "text-fg-1",
    },
    {
      label: "Error code",
      value: trace.error_code ?? "None reported",
      meaning: "The code the proxy or provider attached, verbatim.",
      class: trace.error_code ? "text-crit" : "text-fg-1",
    },
  ]
})

/** Completeness chips for this page, ranked by count; publication counts live in the attention line. */
const completenessChips = computed(() =>
  [...pageCounts.value.entries()]
    .filter(([key]) => !key.startsWith("publication:"))
    .map(([key, count]) => ({ completeness: key.split(":")[1] as TraceCompleteness, count }))
    .sort((left, right) => right.count - left.count),
)
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">
    <ConsolePageHeader
      title="Explore"
      definition="Trace metadata and evidence freshness for your organization — what was captured, how complete the capture was, and whether the evidence row behind it was published."
      :state="headerState"
      :observed="traces?.observed_at ?? null"
      :scope="demoActive ? 'ibex-demo · illustrative development read' : `Current organization · ${resultText || 'no page read'}`"
      :contract="EXPLORE_TRACE_LIST_CONTRACT"
      :verdict="
        demoActive
          ? 'Illustrative development data. The operator API is not connected in this environment, so this page is showing recorded trace fixtures. It is not a live trace read and makes no production claim.'
          : traces
            ? 'Trace metadata is served live from the tenant-scoped query. Payload content is never part of this contract, so nothing here is estimated.'
            : 'The live query did not resolve. No preview rows are substituted for it.'
      "
      :range="
        traces
          ? `Server-bounded window ${formatGovernStamp(traces.query_start)} → ${formatGovernStamp(traces.query_end)}`
          : 'Server-bounded time range'
      "
      :coverage="`${EXPLORE_QUERY_GRAMMAR} · allowlisted fields only`"
      :notes="EXPLORE_LIST_NOTES"
    />

    <p v-if="traces" class="font-mono text-[0.6875rem] leading-4 text-fg-3">
      {{ formatGovernStamp(traces.query_start) }} → {{ formatGovernStamp(traces.query_end) }}
      <span v-if="traces.matched_count === null"> · total matched is not reported by this contract</span>
    </p>

    <p v-if="queryError" class="text-xs leading-4 text-crit" role="alert">
      Invalid query: {{ queryError }}. Nothing was fetched.
    </p>

    <!-- Saved views: the same URL the query box writes. -->
    <nav class="flex flex-wrap items-center gap-1.5" aria-label="Saved views">
      <span class="mr-1 text-[0.6875rem] font-medium tracking-wide text-fg-3 uppercase">Saved views</span>
      <button
        v-for="view in savedViews"
        :key="view.label"
        type="button"
        class="inline-flex h-7 items-center rounded-full border px-2.5 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        :class="viewActive(view.patch)
          ? 'border-accent/40 bg-accent-tint text-fg-1'
          : 'border-line-subtle text-fg-3 hover:border-line hover:text-fg-1'"
        :aria-pressed="viewActive(view.patch)"
        :title="view.hint"
        @click="go(view.patch)"
      >
        {{ view.label }}
      </button>
    </nav>

    <GovernFilterBar
      ref="search"
      v-model="queryInput"
      label="Trace query"
      placeholder="status:error completeness:partial trace:…"
      :result-text="resultText"
      :active="activeFilterCount > 0 || queryInput.trim() !== ''"
      @submit="applyQuery"
      @clear="clearFilters"
    >
      <template #filters>
        <GovernFilterSelect
          label="Status"
          :model-value="parsed?.status ?? 'all'"
          :options="statusOptions"
          default-value="all"
          @update:model-value="go({ status: $event === 'all' ? null : ($event as 'ok' | 'error') })"
        />
        <GovernFilterSelect
          label="Completeness"
          :model-value="parsed?.completeness ?? 'all'"
          :options="completenessSelectOptions"
          default-value="all"
          @update:model-value="go({ completeness: $event === 'all' ? null : ($event as TraceCompleteness) })"
        />
        <GovernFilterSelect
          label="Page size"
          :model-value="String(parsed?.limit ?? 50)"
          :options="limitOptions"
          default-value="50"
          @update:model-value="go({ limit: Number($event), cursor: null })"
        />
        <button
          type="button"
          class="inline-flex h-8 items-center rounded-md border border-line-subtle px-2.5 text-xs text-fg-2 transition-colors hover:border-line hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
          @click="applyQuery"
        >
          Apply query
        </button>
      </template>
      <template #right>
        <GovernCopyId :id="listHref" label="Link to this query" display="copy link" truncate />
      </template>
    </GovernFilterBar>

    <section v-if="traces && items.length" class="grid gap-3 sm:grid-cols-2" aria-label="Result composition">
      <div class="console-panel p-3">
        <CompositionBar title="Run outcome" :segments="outcomeSegments" />
      </div>
      <div class="console-panel p-3">
        <CompositionBar title="Capture completeness" :segments="completenessSegments" />
      </div>
    </section>

    <!-- Counts on this page only; the contract exposes no corpus-wide aggregate. -->
    <section
      v-if="items.length > 0"
      class="flex flex-wrap items-center gap-2 text-[0.6875rem] text-fg-3"
      aria-label="What is on this page"
    >
      <span>{{ attention.errors }} failed · {{ attention.incomplete }} incomplete · {{ attention.sampled }} sampled</span>
      <button
        v-for="chip in completenessChips"
        :key="chip.completeness"
        type="button"
        class="inline-flex h-6 items-center gap-1.5 rounded-full border px-2 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        :class="chip.completeness === 'complete'
          ? 'border-line-subtle text-fg-3 hover:text-fg-1'
          : 'border-warn/40 bg-warn-tint text-warn'"
        :title="COMPLETENESS_MEANING[chip.completeness]"
        @click="go({ completeness: chip.completeness, status: null })"
      >
        <span class="font-mono text-xs leading-5 font-semibold tabular-nums">{{ chip.count }}</span>
        {{ COMPLETENESS_LABELS[chip.completeness] }}
      </button>
      <NuxtLink
        v-if="attention.brokenPublication > 0"
        to="/evidence?tab=chain"
        class="inline-flex h-6 items-center gap-1.5 rounded-full border border-crit/40 bg-crit-tint px-2 text-xs text-crit transition-colors hover:border-crit/60"
        title="Publication did not produce a usable evidence row. The chain tab shows where the trail stops."
      >
        <span class="font-mono text-xs leading-5 font-semibold tabular-nums">{{ attention.brokenPublication }}</span>
        publication broken → evidence chain
      </NuxtLink>
    </section>

    <div class="min-w-0">
      <div v-if="authIssue" class="rounded-lg border border-warn/40 bg-warn-tint p-4">
        <p class="text-sm font-medium text-fg-1">Operator session required</p>
        <p class="mt-1 text-xs leading-4 text-fg-2">
          The access cookie is missing, expired, or lacks metadata-read permission. Nothing is substituted for it here.
        </p>
      </div>

      <GovernCaveat v-else-if="!parsed" tone="warning" title="Query refused before it was sent">
        {{ queryError ?? "Fix the query to load trace metadata." }} The console does not guess at a wider search than you asked for.
      </GovernCaveat>

      <GovernCaveat v-else-if="tracesFailed" tone="warning" title="Trace metadata unavailable">
        The run may not exist in this organization, may have expired under retention, or the upstream read failed. Empty
        rows are not drawn from a fixture.
      </GovernCaveat>

      <div v-else-if="!traces" class="rounded-lg border border-line-subtle bg-surface-1 px-4 py-8 text-center">
        <p class="text-sm font-medium text-fg-1">Reading trace metadata</p>
        <p class="mt-1 text-xs leading-4 text-fg-3">
          The list appears when the tenant-scoped query resolves. operator.trace-list.v1 · operator.trace-query.v1
        </p>
      </div>

      <GovernEmptyState
        v-else-if="items.length === 0"
        title="No runs match this query"
        reason="An empty page is a valid answer. It means nothing matched the filters within the organization scope — not that the read failed."
        next-step="Widen the time bounds, drop the completeness filter, or check that the run id belongs to this organization."
        action-label="Clear all filters"
        @action="clearFilters"
      />

      <div v-else class="ix-scroll overflow-x-auto rounded-lg border border-line-subtle">
        <table class="ix-agent-table table-fixed" style="min-width: 1052px" aria-label="Trace runs">
          <thead>
            <tr>
              <th scope="col" style="width: 150px">Certification</th>
              <th scope="col" style="width: 180px">Run · trace</th>
              <th scope="col" style="width: 150px">Status</th>
              <th scope="col" style="width: 170px">Completeness</th>
              <th scope="col" style="width: 120px">Freshness</th>
              <th scope="col" style="width: 116px" class="text-right">Duration</th>
              <th scope="col" style="width: 130px">Started</th>
              <th scope="col" style="width: 36px"><span class="sr-only">Peek</span></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in triageRows"
              :key="row.id"
              v-bind="triage.rowAttrs(row)"
              :data-edge="
                row.trace.status === 'error' || BROKEN_PUBLICATION.includes(row.trace.evidence.publication_state)
                  ? 'critical'
                  : row.trace.evidence.completeness === 'complete'
                    ? undefined
                    : 'warning'
              "
            >
              <td>
                <span class="flex items-center gap-1.5" :title="tierForTrace(row.trace).meaning">
                  <IxTierMark
                    :tier="tierForTrace(row.trace).tier"
                    :detail="tierForTrace(row.trace).detail"
                    :record-id="row.trace.run_id"
                  />
                  <span class="truncate text-[0.6875rem] text-fg-2">{{ tierForTrace(row.trace).label }}</span>
                </span>
              </td>
              <td>
                <NuxtLink
                  :to="detailHref('r', row.trace.run_id)"
                  class="ix-link block truncate font-mono text-xs leading-5"
                  :title="row.trace.run_id"
                >
                  {{ shortenId(row.trace.run_id) }}
                </NuxtLink>
                <span class="mt-0.5 block truncate font-mono text-[0.625rem] leading-4 text-fg-3" :title="row.trace.trace_id">
                  {{ row.trace.trace_id }}
                </span>
              </td>
              <td>
                <span
                  class="inline-flex items-center gap-1.5 text-xs"
                  :class="row.trace.status === 'error' ? 'text-crit' : 'text-fg-2'"
                  :title="TRACE_STATUS_MEANING[row.trace.status]"
                >
                  <span class="size-1.5 rounded-full" :class="row.trace.status === 'error' ? 'bg-crit' : 'bg-ok'" aria-hidden="true" />
                  {{ TRACE_STATUS_LABELS[row.trace.status] }}
                </span>
                <span v-if="row.trace.error_code" class="mt-0.5 block truncate font-mono text-[0.625rem] leading-4 text-crit" :title="row.trace.error_code">
                  {{ row.trace.error_code }}
                </span>
              </td>
              <td>
                <span class="block truncate text-xs" :class="completenessClass(row.trace.evidence.completeness)" :title="COMPLETENESS_MEANING[row.trace.evidence.completeness]">
                  {{ COMPLETENESS_LABELS[row.trace.evidence.completeness] }}
                </span>
                <span
                  class="mt-0.5 block truncate text-[0.625rem] leading-4"
                  :class="publicationClass(row.trace.evidence.publication_state)"
                  :title="PUBLICATION_MEANING[row.trace.evidence.publication_state]"
                >
                  {{ PUBLICATION_LABELS[row.trace.evidence.publication_state] }}
                </span>
              </td>
              <td>
                <span class="text-xs" :class="freshnessClass(row.trace.evidence.freshness)" :title="FRESHNESS_MEANING[row.trace.evidence.freshness]">
                  {{ FRESHNESS_LABELS[row.trace.evidence.freshness] }}
                </span>
              </td>
              <td class="whitespace-nowrap text-right font-mono text-xs text-fg-2 tabular-nums">
                {{ row.trace.duration_ms === null ? "Not recorded" : formatDuration(row.trace.duration_ms) }}
              </td>
              <td>
                <span class="whitespace-nowrap text-xs text-fg-2" :title="formatGovernStamp(row.trace.started_at)">
                  {{ formatGovernRelative(row.trace.started_at) }}
                </span>
              </td>
              <td style="padding-left: 0.25rem; padding-right: 0" class="text-right">
                <button
                  type="button"
                  class="inline-flex size-7 items-center justify-center rounded text-fg-3 transition-colors hover:bg-surface-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                  :aria-label="`Peek run ${row.trace.run_id}`"
                  @click.stop="peek(row.trace)"
                >
                  <ChevronRight :size="14" :stroke-width="1.9" aria-hidden="true" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="traces && items.length > 0" class="mt-2 flex flex-wrap items-center justify-between gap-2">
        <p class="text-[0.6875rem] leading-4 text-fg-3">
          {{ traces.truncated
            ? "This contract pages by cursor and does not report a total, so the count beyond this page is unknown."
            : "Every matched run is on this page." }}
          <span v-if="traces.next_cursor && !traces.truncated"> A cursor was returned even though the result is not truncated.</span>
        </p>
        <div class="flex items-center gap-2">
          <NuxtLink
            v-if="parsed?.cursor"
            :to="firstHref"
            class="inline-flex h-8 items-center rounded-md border border-line-subtle px-2.5 text-xs text-fg-2 transition-colors hover:border-line hover:text-fg-1"
          >
            First page
          </NuxtLink>
          <NuxtLink
            v-if="nextHref"
            :to="nextHref"
            class="inline-flex h-8 items-center gap-1 rounded-md border border-line-subtle px-2.5 text-xs text-fg-2 transition-colors hover:border-line hover:text-fg-1"
          >
            Next page
            <ArrowRight :size="13" :stroke-width="1.9" aria-hidden="true" />
          </NuxtLink>
        </div>
      </div>
    </div>

    <GovernCaveat tone="info" title="Facets this page will not offer">
      Agent, duration, span-level and retrieved-content facets have no contract behind them. They are absent rather than
      estimated from the rows currently on screen, because a facet built from one page would misrepresent the whole.
    </GovernCaveat>

    <GovernPeekSheet
      v-if="peekRow"
      v-model:open="peekOpen"
      :title="peekRow.trace.run_id"
      :description="`Run ${peekRow.trace.run_id} · ${formatGovernStamp(peekRow.trace.started_at)}`"
      :href="detailHref('r', peekRow.trace.run_id)"
      href-label="Open run in Explore"
    >
      <dl class="grid gap-2 sm:grid-cols-2">
        <div
          v-for="fact in peekFacts"
          :key="fact.label"
          class="rounded-lg border border-line-subtle bg-surface-2 px-3 py-2"
        >
          <dt class="text-[0.6875rem] text-fg-3">{{ fact.label }}</dt>
          <dd class="mt-0.5 text-xs font-medium" :class="fact.class">{{ fact.value }}</dd>
          <p class="mt-0.5 text-[0.6875rem] leading-4 text-fg-3">{{ fact.meaning }}</p>
        </div>
      </dl>
    </GovernPeekSheet>

    <GovernShortcutsDialog v-model:open="helpOpen" :groups="shortcutGroups" />
  </div>
</template>
