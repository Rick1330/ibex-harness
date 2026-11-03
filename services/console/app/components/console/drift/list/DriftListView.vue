<script setup lang="ts">
import { computed, ref } from "vue"
import { TriangleAlert, UserRound } from "@lucide/vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernFilterBar from "@/components/console/govern/primitives/GovernFilterBar.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import GovernPeekSheet from "@/components/console/govern/primitives/GovernPeekSheet.vue"
import GovernSeverityChip from "@/components/console/govern/primitives/GovernSeverityChip.vue"
import GovernShortcutsDialog from "@/components/console/govern/primitives/GovernShortcutsDialog.vue"
import GovernSparkline from "@/components/console/govern/primitives/GovernSparkline.vue"
import GovernStateChip from "@/components/console/govern/primitives/GovernStateChip.vue"
import DriftListHeader from "./DriftListHeader.vue"
import { useGovernShortcuts } from "@/composables/useGovernShortcuts"
import { useTriageTable } from "@/composables/useTriageTable"
import { formatGovernDate, formatGovernStamp, formatGovernRelative, GOVERN_NOW } from "@/lib/govern-format"
import {
  DRIFT_LIST_DEFAULT,
  DRIFT_SEVERITY_FILTERS,
  DRIFT_SORTS,
  DRIFT_STATE_FILTERS,
  driftListHref,
  driftSignalHref,
  type DriftListState,
} from "@/lib/govern-query"
import {
  DRIFT_SEVERITY_LABELS,
  DRIFT_STATE_LABELS,
  driftAgentOptions,
  driftAttention,
  driftChange,
  driftOwnerOptions,
  driftSignals,
  driftSummarySentence,
  driftSuspectedCauses,
  filterDriftSignals,
  formatDriftValue,
  sortDriftSignals,
  type DriftSignal,
  type DriftSeverity,
  type DriftState,
} from "@/lib/drift-preview"

const props = defineProps<{ state: DriftListState }>()
const emit = defineEmits<{ update: [state: DriftListState] }>()

function update(patch: Partial<DriftListState>): void {
  emit("update", { ...props.state, ...patch })
}

const header = ref<InstanceType<typeof DriftListHeader> | null>(null)
const search = ref<InstanceType<typeof GovernFilterBar> | null>(null)
const attention = computed(() => driftAttention())

const stateOptions = [
  { value: "active", label: "Open or acknowledged" },
  { value: "all", label: "All signals" },
  ...(DRIFT_STATE_FILTERS.filter((entry) => entry !== "active" && entry !== "all") as DriftState[]).map((entry) => ({
    value: entry,
    label: DRIFT_STATE_LABELS[entry],
  })),
]

const severityOptions = DRIFT_SEVERITY_FILTERS.map((value) => ({
  value,
  label: value === "all" ? "All severities" : DRIFT_SEVERITY_LABELS[value as DriftSeverity],
}))

const ownerOptions = computed(() => [
  { value: "all", label: "All owners" },
  { value: "none", label: "No owner" },
  ...driftOwnerOptions().map((owner) => ({ value: owner, label: owner })),
])

const agentOptions = computed(() => [
  { value: "all", label: "All agents" },
  ...driftAgentOptions().map((entry) => ({ value: entry.id, label: entry.label })),
])

const sortOptions = DRIFT_SORTS.map((value) => ({
  value,
  label: value === "severity" ? "Severity, then oldest" : value === "opened" ? "Oldest first" : "Biggest change",
}))

const filtered = computed(() => filterDriftSignals(driftSignals, props.state))
const rows = computed(() => sortDriftSignals(filtered.value, props.state.sort))

const activeFilters = computed(() =>
  [
    props.state.q.trim(),
    props.state.state !== DRIFT_LIST_DEFAULT.state,
    props.state.severity !== "all",
    props.state.owner !== "all",
    props.state.agent !== "all",
    props.state.cause !== "all",
  ].filter(Boolean).length,
)

const peekId = ref<string | null>(null)
const peekOpen = ref(false)
const peekSignal = computed(() => rows.value.find((signal) => signal.id === peekId.value) ?? null)

const triage = useTriageTable({
  rows,
  enabled: () => !peekOpen.value,
  onOpen: (signal) => void navigateTo(driftSignalHref(signal.id)),
  onPeek: (signal) => {
    peekId.value = signal.id
    peekOpen.value = true
  },
})

function clearFilters(): void {
  emit("update", { ...DRIFT_LIST_DEFAULT, sort: props.state.sort })
}

function showAll(): void {
  update({ state: "all" })
}

function copyCurrentLink(): void {
  if (!import.meta.client) return
  void navigator.clipboard.writeText(`${window.location.origin}${driftListHref(props.state)}`)
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
    title: "Move",
    rows: [
      { keys: "j / k", label: "Next / previous signal" },
      { keys: "Enter", label: "Open the selected signal" },
      { keys: "Space", label: "Open the 480px peek" },
      { keys: "/", label: "Focus search" },
      { keys: "Esc", label: "Close the peek or clear selection" },
    ],
  },
  {
    title: "This page",
    rows: [
      { keys: "y", label: "Copy link to this view" },
      { keys: "g p", label: "Go to policies" },
      { keys: "g d", label: "Go to drift" },
      { keys: "g a", label: "Go to audit log" },
      { keys: "?", label: "Show this sheet" },
    ],
  },
]

function causeLabel(signal: DriftSignal): string {
  const cause = driftSuspectedCauses(signal)[0]
  return cause ? `${cause.label} · ${formatGovernDate(cause.cause.at)}` : "No recorded change in 72h"
}

function causeTitle(signal: DriftSignal): string | null {
  return driftSuspectedCauses(signal)[0]?.cause.title ?? null
}
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">
    <DriftListHeader ref="header" />

    <div class="grid gap-2 sm:grid-cols-3">
      <button
        type="button"
        class="flex min-w-0 flex-col rounded-lg border px-3 py-2.5 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        :class="state.owner === 'none' && state.state === 'active' ? 'border-warn/40 bg-warn-tint/40' : 'border-line-subtle bg-surface-1 hover:border-line'"
        @click="update({ state: 'active', owner: 'none' })"
      >
        <span class="flex items-center gap-1.5 text-[0.6875rem] font-medium text-fg-3">
          <UserRound :size="12" :stroke-width="1.9" aria-hidden="true" />
          Needs an owner
        </span>
        <span class="mt-1 flex items-baseline gap-2">
          <span class="ix-kpi" :class="attention.needsOwner.count ? 'text-fg-1' : 'text-fg-2'">{{ attention.needsOwner.count }}</span>
          <span class="text-xs text-fg-3">{{ attention.needsOwner.critical }} critical</span>
        </span>
        <span class="mt-0.5 text-[0.6875rem] leading-4 text-fg-3">
          {{ attention.needsOwner.count ? "Open signals nobody has picked up." : "Every open signal has an owner." }}
        </span>
      </button>

      <button
        type="button"
        class="flex min-w-0 flex-col rounded-lg border px-3 py-2.5 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        :class="state.state === 'active' && state.sort === 'change' ? 'border-warn/40 bg-warn-tint/40' : 'border-line-subtle bg-surface-1 hover:border-line'"
        @click="update({ state: 'active', sort: 'change' })"
      >
        <span class="flex items-center gap-1.5 text-[0.6875rem] font-medium text-fg-3">
          <TriangleAlert :size="12" :stroke-width="1.9" aria-hidden="true" />
          Out of band now
        </span>
        <span class="mt-1 flex items-baseline gap-2">
          <span class="ix-kpi" :class="attention.outOfBand.count ? 'text-warn' : 'text-fg-2'">{{ attention.outOfBand.count }}</span>
          <span v-if="attention.outOfBand.worst" class="font-mono text-[0.6875rem] text-fg-3">
            worst {{ driftChange(attention.outOfBand.worst).label }}
          </span>
        </span>
        <span class="mt-0.5 text-[0.6875rem] leading-4 text-fg-3">
          {{ attention.outOfBand.worst ? attention.outOfBand.worst.metric : "Every active signal is inside its band." }}
        </span>
      </button>

      <button
        type="button"
        class="flex min-w-0 flex-col rounded-lg border px-3 py-2.5 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        :class="state.cause === 'recent' ? 'border-accent/40 bg-accent-tint' : 'border-line-subtle bg-surface-1 hover:border-line'"
        @click="update({ state: 'active', cause: 'recent' })"
      >
        <span class="flex items-center gap-1.5 text-[0.6875rem] font-medium text-fg-3">
          <TriangleAlert :size="12" :stroke-width="1.9" aria-hidden="true" />
          Recent changes with drift after
        </span>
        <span class="mt-1 flex items-baseline gap-2">
          <span class="ix-kpi text-fg-1">{{ attention.recentChanges.count }}</span>
          <span v-if="attention.recentChanges.label" class="truncate text-[0.6875rem] text-fg-3" :title="attention.recentChanges.label">
            {{ attention.recentChanges.label }}
          </span>
        </span>
        <span class="mt-0.5 text-[0.6875rem] leading-4 text-fg-3">
          A recorded change in the 72 hours before the first out-of-band point.
        </span>
      </button>
    </div>

    <GovernFilterBar
      ref="search"
      :model-value="state.q"
      label="Search drift signals"
      placeholder="Search metric, agent, or description"
      :result-text="`${rows.length} of ${driftSignals.length} signals`"
      :active="activeFilters > 0"
      @update:model-value="update({ q: $event })"
      @clear="clearFilters"
    >
      <template #filters>
        <GovernFilterSelect
          label="State"
          :model-value="state.state"
          :options="stateOptions"
          default-value="active"
          @update:model-value="update({ state: $event as DriftListState['state'] })"
        />
        <GovernFilterSelect
          label="Severity"
          :model-value="state.severity"
          :options="severityOptions"
          default-value="all"
          @update:model-value="update({ severity: $event as DriftListState['severity'] })"
        />
        <GovernFilterSelect
          label="Owner"
          :model-value="state.owner"
          :options="ownerOptions"
          default-value="all"
          @update:model-value="update({ owner: $event })"
        />
        <GovernFilterSelect
          label="Agent"
          :model-value="state.agent"
          :options="agentOptions"
          default-value="all"
          @update:model-value="update({ agent: $event })"
        />
        <GovernFilterSelect
          label="Cause"
          :model-value="state.cause"
          :options="[
            { value: 'all', label: 'Any cause' },
            { value: 'recent', label: 'Has a suspected cause' },
          ]"
          default-value="all"
          @update:model-value="update({ cause: $event as DriftListState['cause'] })"
        />
      </template>
      <template #right>
        <GovernFilterSelect
          label="Sort"
          :model-value="state.sort"
          :options="sortOptions"
          default-value="severity"
          @update:model-value="update({ sort: $event as DriftListState['sort'] })"
        />
      </template>
    </GovernFilterBar>

    <div v-if="rows.length === 0" class="rounded-lg border border-line-subtle bg-surface-1 p-2">
      <GovernEmptyState
        title="No drift signals match these filters"
        :reason="state.state === 'active' ? 'No open or acknowledged signal matches the current filters.' : 'No recorded signal matches the current filters.'"
        next-step="Clear the filters, or include resolved signals to review the full history."
        action-label="Show all signals"
        @action="showAll"
      />
    </div>

    <div v-else class="ix-scroll overflow-x-auto rounded-lg border border-line-subtle">
      <table class="ix-agent-table min-w-[860px]" aria-label="Drift signals">
        <thead>
          <tr>
            <th scope="col" class="min-w-32">Signal</th>
            <th scope="col" class="w-20">Change</th>
            <th scope="col" class="hidden w-20 min-[1280px]:table-cell">Trend</th>
            <th scope="col" class="w-20">Severity</th>
            <th scope="col" class="w-16">Opened</th>
            <th scope="col" class="min-w-32">Suspected cause</th>
            <th scope="col" class="w-20">Owner</th>
            <th scope="col" class="w-36">State</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="signal in rows" :key="signal.id" v-bind="triage.rowAttrs(signal)">
            <td>
              <NuxtLink
                :to="driftSignalHref(signal.id)"
                class="text-[0.8125rem] font-medium text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline"
              >
                {{ signal.metric }}
              </NuxtLink>
              <span class="mt-0.5 block text-[0.6875rem] text-fg-3">
                {{ signal.agent.name }} · {{ signal.agent.version }}
              </span>
            </td>
            <td>
              <span class="block font-mono text-xs font-medium text-fg-1 tabular-nums">{{ driftChange(signal).label }}</span>
              <span class="mt-0.5 block text-[0.625rem] text-fg-3">
                {{ formatDriftValue(signal.observed, signal.unit) }}
              </span>
            </td>
            <td class="hidden min-[1280px]:table-cell">
              <GovernSparkline
                :points="signal.series.map((point) => point.observed)"
                :label="`${signal.metric} trend`"
                :band="{ low: signal.baseline - signal.tolerance, high: signal.baseline + signal.tolerance }"
                :width="48"
                :height="18"
              />
            </td>
            <td><GovernSeverityChip :severity="signal.severity" /></td>
            <td>
              <span class="text-xs text-fg-2" :title="formatGovernStamp(signal.openedAt)">
                {{ formatGovernRelative(signal.openedAt, GOVERN_NOW) }}
              </span>
            </td>
            <td>
              <span class="block truncate text-xs text-fg-2" :title="causeTitle(signal) ?? undefined">
                {{ causeLabel(signal) }}
              </span>
              <span v-if="causeTitle(signal)" class="mt-0.5 block max-w-56 truncate text-[0.625rem] text-fg-3" :title="causeTitle(signal) ?? undefined">
                {{ causeTitle(signal) }}
              </span>
            </td>
            <td>
              <span v-if="signal.owner" class="whitespace-nowrap text-xs text-fg-2">{{ signal.owner }}</span>
              <span v-else class="inline-flex items-center gap-1 whitespace-nowrap text-xs text-warn">
                <UserRound :size="11" :stroke-width="2" aria-hidden="true" />
                No owner
              </span>
            </td>
            <td><GovernStateChip :state="signal.state" /></td>
          </tr>
        </tbody>
      </table>
    </div>

    <p class="text-[0.6875rem] leading-4 text-fg-3">
      Default view shows open and acknowledged signals, sorted by severity then oldest. Bands use the certified baseline ± tolerance.
    </p>

    <GovernPeekSheet
      v-if="peekSignal"
      v-model:open="peekOpen"
      :title="peekSignal.metric"
      :description="`${peekSignal.agent.name} · ${peekSignal.agent.version}`"
      :href="driftSignalHref(peekSignal.id)"
      href-label="Open the full signal"
    >
      <div class="flex flex-col gap-3">
        <div class="flex flex-wrap items-center gap-2">
          <GovernSeverityChip :severity="peekSignal.severity" />
          <GovernStateChip :state="peekSignal.state" />
          <span class="text-xs text-fg-3">Opened {{ formatGovernStamp(peekSignal.openedAt) }}</span>
        </div>

        <p class="text-sm leading-6 text-fg-2">{{ driftSummarySentence(peekSignal) }}</p>

        <dl class="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line-subtle bg-line-subtle">
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Change</dt>
            <dd class="mt-0.5 font-mono text-sm font-medium text-fg-1">{{ driftChange(peekSignal).label }}</dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Baseline</dt>
            <dd class="mt-0.5 font-mono text-sm text-fg-2">{{ formatDriftValue(peekSignal.baseline, peekSignal.unit) }}</dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Band</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-2">
              {{ formatDriftValue(peekSignal.baseline - peekSignal.tolerance, peekSignal.unit) }} –
              {{ formatDriftValue(peekSignal.baseline + peekSignal.tolerance, peekSignal.unit) }}
            </dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Threshold</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-2">{{ formatDriftValue(peekSignal.threshold, peekSignal.unit) }}</dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Owner</dt>
            <dd class="mt-0.5 text-xs" :class="peekSignal.owner ? 'text-fg-1' : 'text-warn'">{{ peekSignal.owner ?? "No owner" }}</dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Monitor</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-2">{{ peekSignal.monitorId }}</dd>
          </div>
        </dl>

        <div>
          <p class="text-xs font-medium text-fg-1">Suspected causes</p>
          <ul v-if="driftSuspectedCauses(peekSignal).length" class="mt-1.5 divide-y divide-line-subtle rounded-lg border border-line-subtle">
            <li v-for="cause in driftSuspectedCauses(peekSignal)" :key="cause.cause.id" class="px-3 py-2">
              <p class="text-xs font-medium text-fg-1">{{ cause.cause.title }}</p>
              <p class="mt-0.5 text-[0.6875rem] text-fg-3">{{ cause.label }} · {{ formatGovernStamp(cause.cause.at) }}</p>
            </li>
          </ul>
          <p v-else class="mt-1.5 text-xs leading-5 text-fg-3">
            No recorded change in the 72 hours before the first out-of-band point.
          </p>
        </div>

        <NuxtLink :to="driftSignalHref(peekSignal.id)" class="ix-button-secondary h-8 w-fit px-3 text-xs">
          Open overview
        </NuxtLink>
      </div>
    </GovernPeekSheet>

    <GovernShortcutsDialog v-model:open="helpOpen" :groups="shortcutGroups" />
  </div>
</template>
