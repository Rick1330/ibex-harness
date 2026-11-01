<script setup lang="ts">
import { computed, ref } from "vue"
import { ArrowLeft, ChevronRight, Gauge } from "@lucide/vue"
import GovernAboutPopover from "@/components/console/govern/primitives/GovernAboutPopover.vue"
import GovernDataSourceChip from "@/components/console/govern/primitives/GovernDataSourceChip.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernEvidenceChip from "@/components/console/govern/primitives/GovernEvidenceChip.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import { formatGovernShortDate, formatGovernStamp } from "@/lib/govern-format"
import {
  driftBaselineAge,
  driftBaselineTone,
  driftBaselines,
  driftSignalsForBaseline,
  type DriftBaseline,
} from "@/lib/drift-preview"
import {
  driftBaselineHref,
  driftListHref,
  driftMonitorListHref,
  DRIFT_BASELINE_AGE_LABELS,
  DRIFT_BASELINE_AGES,
  DRIFT_LIST_DEFAULT,
  type DriftBaselineListState,
} from "@/lib/govern-query"

const props = defineProps<{ state: DriftBaselineListState }>()
const emit = defineEmits<{ update: [state: DriftBaselineListState] }>()

const about = ref<InstanceType<typeof GovernAboutPopover> | null>(null)

function update(patch: Partial<DriftBaselineListState>): void {
  emit("update", { ...props.state, ...patch })
}

const agentOptions = computed(() => [
  { value: "all", label: "All agents" },
  ...driftBaselines.map((baseline) => ({
    value: baseline.agent.id,
    label: `${baseline.agent.name} · ${baseline.agent.version}`,
  })),
])

const ageOptions = DRIFT_BASELINE_AGES.map((value) => ({ value, label: DRIFT_BASELINE_AGE_LABELS[value] }))

type BaselineRow = {
  baseline: DriftBaseline
  age: number | null
  tone: "ok" | "warning" | "critical"
  open: number
}

const rows = computed<BaselineRow[]>(() =>
  driftBaselines.map((baseline) => ({
    baseline,
    age: driftBaselineAge(baseline),
    tone: driftBaselineTone(baseline),
    open: driftSignalsForBaseline(baseline.id).length,
  })),
)

const filtered = computed(() =>
  rows.value.filter((row) => {
    if (props.state.agent !== "all" && row.baseline.agent.id !== props.state.agent) return false
    if (props.state.age === "stale" && (row.age ?? 0) <= 30) return false
    if (props.state.age === "expired" && (row.age ?? 0) <= 90) return false
    return true
  }),
)

function ageLabel(row: BaselineRow): string {
  return row.age === null ? "Not recorded" : `${row.age} ${row.age === 1 ? "day" : "days"}`
}

function ageClass(row: BaselineRow): string {
  if (row.tone === "critical") return "text-crit"
  if (row.tone === "warning") return "text-warn"
  return "text-fg-2"
}

function clearFilters(): void {
  emit("update", { agent: "all", age: "all" })
}
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">

    <header class="flex flex-col gap-3">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <NuxtLink
            :to="driftListHref(DRIFT_LIST_DEFAULT)"
            class="inline-flex items-center gap-1.5 rounded text-xs text-fg-3 transition-colors hover:text-fg-1"
          >
            <ArrowLeft :size="13" :stroke-width="1.9" aria-hidden="true" />
            Back to drift
          </NuxtLink>
          <div class="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
            <h1 class="ix-page-title text-fg-1">Baselines</h1>
                      </div>
          <p class="mt-1 max-w-2xl text-sm leading-5 text-fg-2">
            The certified behaviour each agent version is measured against, and when it was last certified.
          </p>
        </div>

        <div class="flex shrink-0 flex-wrap items-center gap-2">
          <GovernDataSourceChip @open="about?.open()" />
    <GovernAboutPopover
      ref="about"
      verdict="Every baseline, window, and certification on this page is an illustrative fixture. No baseline read model is connected to this console."
      contract="operator.drift.baselines.v1"
      scope="org_demo_42 · workspace ws_42"
      range="Certified 20 Jul – 02 Oct 2026"
      coverage="Preview fixtures · no baseline read model connected"
      phase="D5 · Phase B2"
      claim="No enforcement, audit, or billing claim."
      :notes="[
        { lead: 'A baseline is a certified window, not a live average.', body: 'The band is fixed when a person certifies it. The console does not move the band when new runs arrive.' },
        { lead: 'Evidence can be sampled.', body: 'A sampled baseline cites fewer runs than a certified one. Both are labelled; neither is presented as complete.' },
      ]"
    />
          <NuxtLink :to="driftMonitorListHref({ status: 'all', agent: 'all' })" class="ix-button-secondary h-8 gap-1.5 px-2.5 text-xs">
            <Gauge :size="13" :stroke-width="1.8" aria-hidden="true" />
            Monitors
          </NuxtLink>
        </div>
      </div>
    </header>

    <div class="flex flex-wrap items-end justify-between gap-2">
      <div class="flex flex-wrap items-center gap-2">
        <GovernFilterSelect
          label="Agent"
          :model-value="state.agent"
          :options="agentOptions"
          default-value="all"
          @update:model-value="update({ agent: $event })"
        />
        <GovernFilterSelect
          label="Age"
          :model-value="state.age"
          :options="ageOptions"
          default-value="all"
          @update:model-value="update({ age: $event as DriftBaselineListState['age'] })"
        />
      </div>
      <p class="font-mono text-[0.6875rem] text-fg-3">
        {{ filtered.length }} of {{ rows.length }} {{ rows.length === 1 ? "baseline" : "baselines" }}
      </p>
    </div>

    <GovernEmptyState
      v-if="!filtered.length"
      title="No baseline matches these filters"
      reason="Baselines are recorded per agent version; this preview set has three."
      next-step="Clear the filters to see every recorded baseline."
      action-label="Clear filters"
      @action="clearFilters"
    />

    <div v-else class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
      <div class="ix-scroll overflow-x-auto">
        <table class="ix-agent-table" aria-label="Agent baselines">
          <thead>
            <tr>
              <th scope="col" class="min-w-40">Agent</th>
              <th scope="col" class="min-w-36">Certified</th>
              <th scope="col" class="min-w-32">Window</th>
              <th scope="col" class="w-16 text-right">Metrics</th>
              <th scope="col" class="w-24">Evidence</th>
              <th scope="col" class="w-20 text-right">Age</th>
              <th scope="col" class="w-24 text-right">Open signals</th>
              <th scope="col" class="w-10"><span class="sr-only">Open</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in filtered" :key="row.baseline.id">
              <td>
                <NuxtLink
                  :to="driftBaselineHref(row.baseline.agent.id)"
                  class="text-[0.8125rem] font-medium text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline"
                >
                  {{ row.baseline.agent.name }}
                </NuxtLink>
                <p class="mt-0.5 flex items-center gap-1.5 text-[0.625rem] text-fg-3">
                  <span class="font-mono">{{ row.baseline.agent.version }}</span>
                  <span aria-hidden="true">·</span>
                  <span class="font-mono">{{ row.baseline.id }}</span>
                </p>
              </td>
              <td>
                <span class="text-xs text-fg-2">{{ row.baseline.certifiedBy }}</span>
                <p class="mt-0.5 text-[0.625rem] text-fg-3" :title="formatGovernStamp(row.baseline.certifiedAt)">
                  {{ formatGovernShortDate(row.baseline.certifiedAt) }}
                </p>
              </td>
              <td>
                <p class="text-xs text-fg-2">{{ formatGovernShortDate(row.baseline.windowFrom) }} – {{ formatGovernShortDate(row.baseline.windowTo) }}</p>
                <p class="mt-0.5 text-[0.625rem] text-fg-3">{{ row.baseline.runs }} runs</p>
              </td>
              <td class="text-right">
                <span class="font-mono text-xs text-fg-2 tabular-nums">{{ row.baseline.metrics.length }}</span>
              </td>
              <td>
                <GovernEvidenceChip :evidence="row.baseline.evidence" />
              </td>
              <td class="text-right">
                <span class="font-mono text-xs whitespace-nowrap tabular-nums" :class="ageClass(row)">{{ ageLabel(row) }}</span>
              </td>
              <td class="text-right">
                <NuxtLink
                  v-if="row.open"
                  :to="driftListHref({ ...DRIFT_LIST_DEFAULT, agent: row.baseline.agent.id })"
                  class="font-mono text-xs text-fg-1 underline-offset-2 hover:text-accent-memory hover:underline"
                >
                  {{ row.open }}
                </NuxtLink>
                <span v-else class="font-mono text-xs text-fg-3">0</span>
              </td>
              <td>
                <NuxtLink
                  :to="driftBaselineHref(row.baseline.agent.id)"
                  class="inline-flex size-6 items-center justify-center rounded text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                  :aria-label="`Open baseline for ${row.baseline.agent.name} ${row.baseline.agent.version}`"
                >
                  <ChevronRight :size="14" :stroke-width="1.9" aria-hidden="true" />
                </NuxtLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <footer class="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line-subtle bg-canvas/30 px-4 py-1.5 text-[0.6875rem] leading-4 text-fg-3">
        <span>An agent without a baseline is not evaluated for drift. Age is counted from the certification date.</span>
        <span class="ml-auto font-mono">{{ filtered.length }} baselines</span>
      </footer>
    </div>


  </div>
</template>
