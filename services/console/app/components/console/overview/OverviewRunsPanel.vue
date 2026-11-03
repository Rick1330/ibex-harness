<script setup lang="ts">
import { computed, type Ref } from "vue"
import type { PublicOperatorTrace, PublicOperatorTraceList } from "~~/shared/operator/public"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernPendingData from "@/components/console/govern/primitives/GovernPendingData.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import IxTierMark from "@/components/console/IxTierMark.vue"
import { useTriageTable } from "@/composables/useTriageTable"
import { formatDuration, shortenId } from "@/lib/format"
import { formatGovernNumber, formatGovernStamp } from "@/lib/govern-format"
import { tierForTrace } from "@/lib/certification"
import {
  COMPLETENESS_LABELS,
  COMPLETENESS_MEANING,
  PUBLICATION_LABELS,
  PUBLICATION_MEANING,
  TRACE_STATUS_LABELS,
  TRACE_STATUS_MEANING,
  completenessClass,
  publicationClass,
} from "@/lib/explore-view"
import { formatLiveRelative } from "@/lib/live-format"
import { OVERVIEW_RUNS_LIMIT, OVERVIEW_TRACE_CONTRACT } from "@/lib/overview-view"

type RunRow = { id: string; trace: PublicOperatorTrace }

const props = defineProps<{
  traces: PublicOperatorTraceList | null
  loading: boolean
  failed: boolean
  authIssue: boolean
  nowMs: number | null
}>()

const emit = defineEmits<{
  openRun: [runId: string]
  goto: [href: string]
  refresh: []
}>()

const rows: Ref<RunRow[]> = computed(() => (props.traces?.items ?? []).map((trace) => ({ id: trace.run_id, trace })))

const triage = useTriageTable<RunRow>({
  rows,
  onOpen: (row) => emit("openRun", row.id),
  enabled: () => rows.value.length > 0,
})

const windowText = computed(() =>
  props.traces
    ? `${formatGovernStamp(props.traces.query_start)} → ${formatGovernStamp(props.traces.query_end)}`
    : "No query window was observed.",
)
</script>

<template>
  <section class="flex min-w-0 flex-col gap-2.5" aria-label="Recent runs">
    <div class="grid grid-cols-1 gap-2 sm:grid-cols-3">
      <GovernStatTile
        label="Rows returned"
        :value="props.traces ? formatGovernNumber(props.traces.returned_count) : 'Not reported'"
        :helper="
          props.traces
            ? `Read ${formatLiveRelative(props.traces.observed_at, props.nowMs)}`
            : 'operator.trace-list.v1 did not resolve.'
        "
      />
      <GovernStatTile
        label="Matched by the query"
        :value="
          props.traces ? (props.traces.matched_count === null ? 'Not reported' : formatGovernNumber(props.traces.matched_count)) : 'Not reported'
        "
        helper="Shown only when the source itself reports a total"
      />
      <GovernStatTile
        label="Page truncated"
        :value="props.traces ? (props.traces.truncated ? 'Yes' : 'No') : 'Not reported'"
        helper="Yes means rows exist behind the cursor Explore pages through"
      />
    </div>

    <p class="text-[0.6875rem] leading-4 text-fg-3">
      Window {{ windowText }} · the {{ OVERVIEW_RUNS_LIMIT }} newest rows. Explore owns the query language and the paging.
    </p>

    <div v-if="props.authIssue" class="rounded-lg border border-line-subtle bg-surface p-1">
      <GovernEmptyState
        title="Run metadata needs the metadata read permission"
        reason="This session was not granted the operator trace read, so the page shows nothing rather than a sample."
        next-step="The organization snapshot and platform health use their own permissions and are unaffected."
      />
    </div>
    <div v-else-if="props.failed" class="rounded-lg border border-line-subtle bg-surface p-1">
      <GovernEmptyState
        title="Run metadata could not be read"
        reason="The trace list errored for this organization. No earlier page is reused and no rows are invented."
        action-label="Retry this read"
        @action="emit('refresh')"
      />
    </div>
    <GovernPendingData
      v-else-if="props.loading && !props.traces"
      title="Run metadata"
      :contract="OVERVIEW_TRACE_CONTRACT"
      description="Reading the newest rows for this organization."
    />
    <div v-else-if="!rows.length" class="rounded-lg border border-line-subtle bg-surface p-1">
      <GovernEmptyState
        title="No runs inside the default window"
        reason="The source resolved and returned an empty page. An empty page is a valid answer, not a failure."
        action-label="Widen the window in Explore"
        @action="emit('goto', '/explore')"
      />
    </div>

    <div v-else class="ix-scroll min-w-0 overflow-x-auto rounded-lg border border-line-subtle">
      <table class="ix-agent-table table-fixed" style="min-width: 880px" aria-label="Newest runs for this organization">
        <thead>
          <tr>
            <th scope="col" style="width: 30px"><span class="sr-only">Evidence tier</span></th>
            <th scope="col" style="width: 190px">Run</th>
            <th scope="col" style="width: 110px">Status</th>
            <th scope="col" style="width: 170px">Evidence record</th>
            <th scope="col" style="width: 90px" class="text-right">Duration</th>
            <th scope="col" style="width: 120px">Started</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id" v-bind="triage.rowAttrs(row)">
            <td class="pr-0">
              <IxTierMark
                :tier="tierForTrace(row.trace).tier"
                :detail="tierForTrace(row.trace).detail"
                :record-id="row.trace.run_id"
              />
            </td>
            <td>
              <p class="truncate font-mono text-xs leading-5 text-fg-1" :title="row.trace.run_id">{{ shortenId(row.trace.run_id) }}</p>
              <p class="truncate font-mono text-[0.625rem] leading-4 text-fg-3" :title="row.trace.trace_id">{{ row.trace.trace_id }}</p>
            </td>
            <td>
              <span
                class="text-xs"
                :class="row.trace.status === 'error' ? 'text-crit' : 'text-fg-2'"
                :title="TRACE_STATUS_MEANING[row.trace.status]"
              >{{ TRACE_STATUS_LABELS[row.trace.status] }}</span>
            </td>
            <td>
              <span
                class="block truncate text-xs"
                :class="completenessClass(row.trace.evidence.completeness)"
                :title="`${row.trace.evidence.completeness} · ${COMPLETENESS_MEANING[row.trace.evidence.completeness]}`"
              >{{ COMPLETENESS_LABELS[row.trace.evidence.completeness] }}</span>
              <span
                class="block truncate text-[0.6875rem] leading-4"
                :class="publicationClass(row.trace.evidence.publication_state)"
                :title="`${row.trace.evidence.publication_state} · ${PUBLICATION_MEANING[row.trace.evidence.publication_state]}`"
              >{{ PUBLICATION_LABELS[row.trace.evidence.publication_state] }}</span>
            </td>
            <td
              class="text-right font-mono text-xs whitespace-nowrap tabular-nums"
              :class="row.trace.duration_ms === null ? 'text-fg-3' : 'text-fg-2'"
            >{{ row.trace.duration_ms === null ? "Not recorded" : formatDuration(row.trace.duration_ms) }}</td>
            <td
              class="font-mono text-[0.6875rem] leading-4 whitespace-nowrap text-fg-2"
              :title="formatGovernStamp(row.trace.started_at)"
            >{{ formatLiveRelative(row.trace.started_at, props.nowMs) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <GovernCaveat tone="info" title="These rows are a page, not a population">
      Status and evidence values are the platform's own record for each run. Nothing here counts runs that were
      not returned, and a run with no duration written shows <em>Not recorded</em> rather than zero.
      j and k move through the rows, Enter opens the selected run in Explore.
    </GovernCaveat>
  </section>
</template>
