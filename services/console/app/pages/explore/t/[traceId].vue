<script setup lang="ts">
import { computed, ref, watch } from "vue"
import type { PublicOperatorTrace } from "~~/shared/operator/public"
import { ArrowLeft, ChevronRight, Download } from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernIdChip from "@/components/console/govern/primitives/GovernIdChip.vue"
import { useConsoleDemo } from "@/composables/useConsoleDemo"
import { demoTraceRuns } from "@/lib/console-demo"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import GovernShortcutsDialog from "@/components/console/govern/primitives/GovernShortcutsDialog.vue"
import IxVerdict from "@/components/console/IxVerdict.vue"
import IxTierMark from "@/components/console/IxTierMark.vue"
import { useGovernShortcuts } from "@/composables/useGovernShortcuts"
import { useTriageTable } from "@/composables/useTriageTable"
import { formatDuration, shortenId } from "@/lib/format"
import { formatGovernNumber, formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"
import { tierForTrace } from "@/lib/certification"
import { safeExploreReturn } from "@/lib/return-to"
import {
  EXPLORE_TRACE_STATUSES,
  EXPLORE_TRACE_STATUS_LABELS,
  exploreTraceHref,
  parseExploreTraceQuery,
  type ExploreTraceState,
} from "@/lib/govern-query"
import {
  BROKEN_PUBLICATION,
  COMPLETENESS_LABELS,
  COMPLETENESS_MEANING,
  EXPLORE_TRACE_LIST_CONTRACT,
  EXPLORE_TRACE_NOTES,
  FRESHNESS_LABELS,
  PUBLICATION_LABELS,
  TRACE_STATUS_LABELS,
  TRACE_STATUS_MEANING,
  completenessClass,
  exploreAttention,
  freshnessClass,
  publicationClass,
} from "@/lib/explore-view"

const route = useRoute()
const traceId = computed(() => String(route.params.traceId ?? ""))
const returnTo = computed(() => safeExploreReturn(route.query.return))
// The trace page can be entered from a session or a memory, not only from the
// Explore list, so the back target has to name its real destination.
const returnLabel = computed(() => {
  if (returnTo.value.startsWith("/sessions/")) return "Session"
  if (returnTo.value.startsWith("/memories/")) return "Memory"
  return "Explore"
})

// Keyed on the id alone: a new trace must re-read rather than re-label the previous payload,
// while a status change only rewrites the query.
definePageMeta({ key: (pageRoute) => String(pageRoute.params.traceId ?? "") })

const runsState = useTraceRuns(traceId.value)
const demo = useConsoleDemo()
const demoActive = computed(() => demo.value && !runsState.data.value && Boolean(demoTraceRuns(traceId.value)))
const runs = computed(() => runsState.data.value ?? (demoActive.value ? demoTraceRuns(traceId.value) : null))

const state = ref<ExploreTraceState>(parseExploreTraceQuery(route.query))

watch(
  () => route.query,
  () => {
    if (!route.path.startsWith("/explore/t/")) return
    state.value = parseExploreTraceQuery(route.query)
  },
)

function update(next: ExploreTraceState): void {
  state.value = next
  if (!import.meta.client) return
  void navigateTo(exploreTraceHref(traceId.value, next, returnTo.value), { replace: true })
}

useHead(() => ({
  title: `${traceId.value} · Trace runs · IBEX Console`,
}))

const errorStatus = computed(() => {
  const status = (runsState.error.value as { statusCode?: number } | null)?.statusCode
  return status ?? null
})
const authIssue = computed(() => !demoActive.value && (errorStatus.value === 401 || errorStatus.value === 403))
const notFound = computed(() => errorStatus.value === 404)
const reading = computed(() => runs.value === null && !runsState.error.value)

const allRuns = computed<PublicOperatorTrace[]>(() => runs.value?.items ?? [])
const rows = computed<PublicOperatorTrace[]>(() =>
  state.value.status === "all"
    ? allRuns.value
    : allRuns.value.filter((trace) => trace.status === state.value.status),
)

const attention = computed(() => exploreAttention(rows.value))
const headerState = computed<"live" | "partial" | "illustrative">(() => (demoActive.value ? "illustrative" : runs.value && !runsState.error.value ? "live" : "partial"))

const statusLine = computed(() => {
  if (authIssue.value) {
    return { tone: "warning" as const, text: "Operator session required. Trace runs are read with your session; none are inferred client-side." }
  }
  if (runsState.error.value && !demoActive.value) {
    return { tone: "warning" as const, text: "Trace runs unavailable. The trace may not exist in this organization or the upstream read failed. No values are inferred." }
  }
  const value = runs.value
  if (!value) return { tone: "muted" as const, text: "Reading the runs captured for this trace." }
  if (!value.items.length) {
    return { tone: "warning" as const, text: "The trace identifier resolved but returned no runs. An empty trace is not a successful trace." }
  }
  const watch = attention.value
  const problems = watch.errors + watch.incomplete + watch.brokenPublication
  const head = `${formatGovernNumber(value.items.length)} run${value.items.length === 1 ? "" : "s"} returned for this trace`
  const filtered = state.value.status === "all" ? "" : `, ${formatGovernNumber(rows.value.length)} shown after the status filter`
  const tail = problems > 0
    ? `${watch.errors} failed · ${watch.incomplete} incomplete · ${watch.brokenPublication} with broken publication.`
    : "None reported an error."
  return {
    tone: problems > 0 ? ("warning" as const) : ("ok" as const),
    text: `${head}${filtered}. ${tail}`,
  }
})


const verdictTone = computed(() => {
  if (statusLine.value.tone === "ok") return "healthy" as const
  if (statusLine.value.tone === "warning") return "attention" as const
  return "unknown" as const
})
type TraceRow = { id: string; trace: PublicOperatorTrace }

const triageRows = computed<TraceRow[]>(() => rows.value.map((trace) => ({ id: trace.run_id, trace })))

const currentHref = computed(() => exploreTraceHref(traceId.value, state.value, returnTo.value))

function openRun(row: TraceRow): void {
  void navigateTo(`/explore/r/${encodeURIComponent(row.trace.run_id)}?return=${encodeURIComponent(currentHref.value)}`)
}

const triage = useTriageTable({ rows: triageRows, onOpen: openRun })

function backToList(): void {
  void navigateTo(returnTo.value)
}

function copyCurrentLink(): void {
  if (!import.meta.client) return
  void navigator.clipboard.writeText(`${window.location.origin}${currentHref.value}`)
}

const { helpOpen } = useGovernShortcuts({
  onEscape: () => triage.select(null),
  keys: {
    y: copyCurrentLink,
    "0": () => update({ status: "all" }),
    "1": () => update({ status: "ok" }),
    "2": () => update({ status: "error" }),
  },
})

const shortcutGroups = [
  {
    title: "This page",
    rows: [
      { keys: "j / k", label: "Move between runs" },
      { keys: "Enter", label: "Open the run detail" },
      { keys: "0 / 1 / 2", label: "All runs · completed · failed" },
      { keys: "y", label: "Copy link to this view" },
      { keys: "g x", label: "Go to Explore" },
      { keys: "?", label: "Show this sheet" },
    ],
  },
]
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">
    <ConsolePageHeader
      :title="`Trace ${traceId.length > 14 ? `${traceId.slice(0, 12)}…` : traceId}`"
      definition="Every run the platform linked to this trace, inside your organization, with the evidence state of each one."
      :state="headerState"
      :observed="runs?.observed_at ?? null"
      :scope="demoActive ? `ibex-demo · illustrative trace ${traceId}` : `Current organization · trace ${traceId}`"
      :contract="EXPLORE_TRACE_LIST_CONTRACT"
      :verdict="
        demoActive
          ? 'Illustrative development data. The operator API is not connected in this environment, so this trace view is a recorded fixture. It is not a live trace read and makes no production claim.'
          : runs
            ? 'These are the run records the trace query returned for your organization. Grouping under one trace is the platform’s own linkage; each run keeps its own status and evidence state.'
            : 'The trace query did not resolve. No runs are reconstructed from the identifier in the address bar.'
      "
      :range="runs ? `Page observed ${formatGovernStamp(runs.observed_at)}` : 'Trace identifier supplied by the caller'"
      :notes="EXPLORE_TRACE_NOTES"
    >
      <template #back>
        <NuxtLink
          :to="returnTo"
          class="inline-flex items-center gap-1 text-xs text-fg-3 transition-colors hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          <ArrowLeft :size="12" :stroke-width="1.9" aria-hidden="true" />
          {{ returnLabel }}
        </NuxtLink>
      </template>

      <template #eyebrow>
        <div class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
          <span class="font-mono text-[0.6875rem] leading-4 text-fg-3">Investigate · Trace runs</span>
          <GovernIdChip :value="traceId" label="Trace ID" />
        </div>
      </template>

      <template #actions>
        <GovernLockedAction label="Export trace runs" :icon="Download" />
      </template>
    </ConsolePageHeader>

    <IxVerdict
      :tone="verdictTone"
      eyebrow="Current read"
      :title="statusLine.text"
      :meta="runs?.observed_at ? formatGovernStamp(runs.observed_at) : undefined"
    />

    <div class="flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter runs by status">
      <span class="mr-1 text-[0.6875rem] font-medium tracking-wide text-fg-3 uppercase">Filter returned runs</span>
      <button
        v-for="option in EXPLORE_TRACE_STATUSES"
        :key="option"
        type="button"
        class="inline-flex h-7 items-center rounded-full border px-2.5 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        :class="state.status === option
          ? 'border-accent/40 bg-accent-tint text-fg-1'
          : 'border-line-subtle text-fg-3 hover:border-line hover:text-fg-1'"
        :aria-pressed="state.status === option"
        @click="update({ status: option })"
      >
        {{ EXPLORE_TRACE_STATUS_LABELS[option] }}
      </button>
      <span v-if="runs && state.status !== 'all'" class="text-[0.6875rem] leading-4 text-fg-3">
        over the {{ formatGovernNumber(runs.items.length) }} runs this trace returned
      </span>
    </div>

    <div class="min-w-0">
      <div v-if="reading" class="rounded-lg border border-line-subtle bg-surface-1 px-4 py-10 text-center">
        <p class="text-sm font-medium text-fg-1">Reading trace runs</p>
        <p class="mt-1 text-xs leading-4 text-fg-3">
          The table appears when the tenant-scoped trace query resolves. Nothing is drawn from the row that linked here.
        </p>
      </div>

      <GovernEmptyState
        v-else-if="notFound"
        :title="`No trace record for ${traceId.length > 20 ? `${traceId.slice(0, 20)}…` : traceId}`"
        reason="The identifier resolved to nothing inside your organization. Another organization's trace is reported the same way, so existence is not leaked."
        next-step="Check the identifier against the query that produced it."
        :action-label="`Back to ${returnLabel}`"
        @action="backToList"
      />

      <GovernEmptyState
        v-else-if="authIssue"
        title="Operator session required"
        reason="The access cookie is missing, expired, or lacks metadata-read permission. No preview rows are substituted for it."
        next-step="Sign in with an operator account that holds metadata-read permission."
      />

      <GovernEmptyState
        v-else-if="runs && runs.items.length === 0"
        title="No runs returned for this trace"
        reason="The trace identifier resolved, but no run metadata came back. An empty trace is a valid answer, not a successful run."
        next-step="Open Explore and search by session or request id to see whether the work was captured under another grouping."
        :action-label="`Back to ${returnLabel}`"
        @action="backToList"
      />

      <GovernEmptyState
        v-else-if="runs && rows.length === 0"
        title="No run in this trace matches the filter"
        :reason="`All ${formatGovernNumber(runs.items.length)} returned runs are excluded by the current status filter.`"
        next-step="Choose All runs to see the unfiltered set."
        action-label="Show all runs"
        @action="update({ status: 'all' })"
      />

      <GovernEmptyState
        v-else-if="runsState.error.value"
        title="Trace runs unavailable"
        reason="The upstream read failed. The console reports the failure rather than rendering an empty table that looks like an answer."
        next-step="Reload to retry; if it persists, the trace may have expired under retention."
      />

      <div v-else class="ix-scroll overflow-x-auto rounded-lg border border-line-subtle">
        <table class="ix-agent-table table-fixed" style="min-width: 976px" aria-label="Runs in this trace">
          <thead>
            <tr>
              <th scope="col" style="width: 150px">Certification</th>
              <th scope="col" style="width: 156px">Run</th>
              <th scope="col" style="width: 158px">Status</th>
              <th scope="col" style="width: 168px">Completeness</th>
              <th scope="col" style="width: 106px">Freshness</th>
              <th scope="col" style="width: 112px" class="text-right">Duration</th>
              <th scope="col" style="width: 88px">Started</th>
              <th scope="col" style="width: 30px"><span class="sr-only">Open</span></th>
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
                  :to="`/explore/r/${encodeURIComponent(row.trace.run_id)}?return=${encodeURIComponent(currentHref)}`"
                  class="ix-link block truncate font-mono text-xs leading-5"
                  :title="row.trace.run_id"
                >
                  {{ shortenId(row.trace.run_id) }}
                </NuxtLink>
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
                  :title="PUBLICATION_LABELS[row.trace.evidence.publication_state]"
                >
                  {{ PUBLICATION_LABELS[row.trace.evidence.publication_state] }}
                </span>
              </td>
              <td>
                <span class="text-xs" :class="freshnessClass(row.trace.evidence.freshness)">
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
                <ChevronRight :size="13" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <p v-if="runs && runs.items.length > 0" class="mt-2 text-[0.6875rem] leading-4 text-fg-3">
        {{ formatGovernNumber(runs.returned_count) }} run{{ runs.returned_count === 1 ? "" : "s" }} returned by
        {{ EXPLORE_TRACE_LIST_CONTRACT }}
        <span v-if="runs.truncated"> · the result was truncated, so this trace has runs that were not returned.</span>
        <span v-else> · the result was not truncated, so this is the whole trace as the contract sees it.</span>
      </p>
    </div>

    <GovernCaveat tone="lock" title="What a trace does not prove">
      Runs sharing a trace identifier were linked by the platform. That does not mean they share a prompt, a billing
      record, or an outcome — each row keeps its own status, completeness and publication state, and each is read from its
      own evidence record.
    </GovernCaveat>

    <GovernShortcutsDialog v-model:open="helpOpen" :groups="shortcutGroups" />
  </div>
</template>
