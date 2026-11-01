<script setup lang="ts">
import { computed, ref } from "vue"
import { ArrowLeft, ChevronRight, Gauge, Plus } from "@lucide/vue"
import GovernAboutPopover from "@/components/console/govern/primitives/GovernAboutPopover.vue"
import GovernDataSourceChip from "@/components/console/govern/primitives/GovernDataSourceChip.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import GovernPeekSheet from "@/components/console/govern/primitives/GovernPeekSheet.vue"
import GovernSeverityChip from "@/components/console/govern/primitives/GovernSeverityChip.vue"
import GovernShortcutsDialog from "@/components/console/govern/primitives/GovernShortcutsDialog.vue"
import GovernMonitorStatusChip from "@/components/console/drift/GovernMonitorStatusChip.vue"
import { useGovernShortcuts } from "@/composables/useGovernShortcuts"
import { formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"
import {
  driftMonitorValue,
  driftMonitors,
  type DriftMonitor,
  type DriftMonitorStatus,
} from "@/lib/drift-preview"
import {
  driftListHref,
  DRIFT_LIST_DEFAULT,
  DRIFT_MONITOR_STATUS_FILTERS,
  DRIFT_MONITOR_STATUS_LABELS,
  type DriftMonitorListState,
} from "@/lib/govern-query"

const props = defineProps<{ state: DriftMonitorListState }>()
const emit = defineEmits<{ update: [state: DriftMonitorListState] }>()

const about = ref<InstanceType<typeof GovernAboutPopover> | null>(null)

function update(patch: Partial<DriftMonitorListState>): void {
  emit("update", { ...props.state, ...patch })
}

const agentOptions = computed(() => {
  const labels = [...new Set(driftMonitors.flatMap((monitor) => monitor.appliesTo))]
  return [
    { value: "all", label: "All agents" },
    ...labels.map((label) => ({ value: label, label: label === "All agents" ? "All agents (every version)" : label })),
  ]
})

const statusOptions = DRIFT_MONITOR_STATUS_FILTERS.map((value) => ({
  value,
  label: value === "all" ? "Any status" : DRIFT_MONITOR_STATUS_LABELS[value],
}))

const filtered = computed(() =>
  driftMonitors.filter((monitor) => {
    if (props.state.status !== "all" && monitor.status !== props.state.status) return false
    if (props.state.agent !== "all" && !monitor.appliesTo.includes(props.state.agent)) return false
    return true
  }),
)

const counts = computed(() => {
  const base: Record<DriftMonitorStatus, number> = { firing: 0, ok: 0, no_data: 0, muted: 0 }
  for (const monitor of driftMonitors) base[monitor.status] += 1
  return base
})

const tiles = computed(() => [
  { status: "firing" as const, label: "Firing", tone: "text-crit", detail: "Opened a signal" },
  { status: "no_data" as const, label: "No data", tone: "text-warn", detail: "Nothing evaluated" },
  { status: "muted" as const, label: "Muted", tone: "text-fg-2", detail: "Still evaluating" },
  { status: "ok" as const, label: "OK", tone: "text-ok", detail: "Inside the band" },
])

const peekId = ref<string | null>(null)
const peekOpen = ref(false)
const peekMonitor = computed(() => driftMonitors.find((monitor) => monitor.id === peekId.value) ?? null)
const peekSignalHref = computed(() => (peekMonitor.value?.signalId ? `/drift/signals/${encodeURIComponent(peekMonitor.value.signalId)}` : null))

function openMonitor(monitor: DriftMonitor): void {
  peekId.value = monitor.id
  peekOpen.value = true
}

function toggleStatus(status: DriftMonitorStatus): void {
  update({ status: props.state.status === status ? "all" : status })
}

function clearFilters(): void {
  emit("update", { status: "all", agent: "all" })
}

const { helpOpen } = useGovernShortcuts({
  onEscape: () => {
    if (peekOpen.value) peekOpen.value = false
  },
})

const shortcutGroups = [
  {
    title: "This page",
    rows: [
      { keys: "Esc", label: "Close the monitor sheet" },
      { keys: "g d", label: "Go to drift" },
      { keys: "g a", label: "Go to audit log" },
      { keys: "?", label: "Show this sheet" },
    ],
  },
]
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
            <h1 class="ix-page-title text-fg-1">Monitors</h1>
                      </div>
          <p class="mt-1 max-w-2xl text-sm leading-5 text-fg-2">
            The checks that compare agent behaviour to a certified baseline and open a signal when it moves.
          </p>
        </div>

        <div class="flex shrink-0 flex-wrap items-center gap-2">
          <GovernDataSourceChip @open="about?.open()" />
    <GovernAboutPopover
      ref="about"
      verdict="Every monitor, evaluation, and notification target on this page is an illustrative fixture. No drift monitor service is connected to this console."
      contract="operator.drift.monitors.v1"
      scope="org_demo_42 · workspace ws_42"
      range="Evaluated 30 Oct 2026, 12:00–15:08 UTC"
      coverage="Preview fixtures · no drift monitor service connected"
      phase="D5 · Phase B2"
      claim="No enforcement, audit, or billing claim."
      :notes="[
        { lead: 'A monitor compares behaviour to a band.', body: 'It evaluates recorded runs against the certified baseline. Firing opens a signal; the signal carries the evidence and the state a person sets.' },
        { lead: 'No data is not a pass.', body: 'A monitor with no recent runs reports No data with a reason. The console never renders a missing evaluation as an OK result.' },
      ]"
    />
          <GovernLockedAction label="New monitor" :icon="Plus" />
        </div>
      </div>
    </header>

    <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <button
        v-for="tile in tiles"
        :key="tile.status"
        type="button"
        class="flex flex-col items-start gap-0.5 rounded-lg border px-3 py-2 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        :class="state.status === tile.status ? 'border-accent/40 bg-accent-tint' : 'border-line-subtle bg-surface-1 hover:border-line'"
        :aria-pressed="state.status === tile.status"
        @click="toggleStatus(tile.status)"
      >
        <span class="text-[0.6875rem] font-medium text-fg-3">{{ tile.label }}</span>
        <span class="font-mono text-xl leading-6 font-semibold tabular-nums" :class="tile.tone">{{ counts[tile.status] }}</span>
        <span class="text-[0.625rem] text-fg-3">{{ tile.detail }}</span>
      </button>
    </div>

    <div class="flex flex-wrap items-end justify-between gap-2">
      <div class="flex flex-wrap items-center gap-2">
        <GovernFilterSelect
          label="Status"
          :model-value="state.status"
          :options="statusOptions"
          default-value="all"
          @update:model-value="update({ status: $event as DriftMonitorListState['status'] })"
        />
        <GovernFilterSelect
          label="Agent"
          :model-value="state.agent"
          :options="agentOptions"
          default-value="all"
          @update:model-value="update({ agent: $event })"
        />
      </div>
      <p class="font-mono text-[0.6875rem] text-fg-3">
        {{ filtered.length }} of {{ driftMonitors.length }} {{ driftMonitors.length === 1 ? "monitor" : "monitors" }}
      </p>
    </div>

    <GovernEmptyState
      v-if="!filtered.length"
      title="No monitor matches these filters"
      reason="Monitors are recorded per agent version and metric."
      next-step="Clear the filters to see every recorded monitor."
      action-label="Clear filters"
      @action="clearFilters"
    />

    <div v-else class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
      <div class="ix-scroll overflow-x-auto">
        <table class="ix-agent-table" aria-label="Drift monitors">
          <thead>
            <tr>
              <th scope="col" class="min-w-44">Monitor</th>
              <th scope="col" class="min-w-32">Applies to</th>
              <th scope="col" class="min-w-32">Rule</th>
              <th scope="col" class="w-24">Severity</th>
              <th scope="col" class="w-32">Last evaluated</th>
              <th scope="col" class="w-28">Status</th>
              <th scope="col" class="w-24">Signal</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="monitor in filtered" :key="monitor.id">
              <td>
                <button
                  type="button"
                  class="group flex max-w-full items-center gap-1.5 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                  :aria-label="`Show evaluations for ${monitor.metric}`"
                  @click="openMonitor(monitor)"
                >
                  <Gauge :size="13" :stroke-width="1.8" class="shrink-0 text-fg-3" aria-hidden="true" />
                  <span class="truncate text-[0.8125rem] font-medium text-fg-1 underline-offset-3 group-hover:underline">{{ monitor.metric }}</span>
                  <ChevronRight :size="12" :stroke-width="1.9" class="shrink-0 text-fg-off transition-colors group-hover:text-fg-2" aria-hidden="true" />
                </button>
                <p class="mt-0.5 max-w-56 truncate text-[0.625rem] text-fg-3" :title="monitor.description">{{ monitor.description }}</p>
              </td>
              <td>
                <div class="flex flex-wrap gap-1">
                  <span
                    v-for="label in monitor.appliesTo"
                    :key="label"
                    class="inline-flex h-5 items-center rounded border border-line-subtle bg-surface-2 px-1.5 text-[0.625rem] text-fg-2"
                  >
                    {{ label }}
                  </span>
                </div>
              </td>
              <td>
                <span class="font-mono text-[0.6875rem] text-fg-2">{{ monitor.rule }}</span>
              </td>
              <td>
                <GovernSeverityChip :severity="monitor.severity" />
              </td>
              <td>
                <span v-if="monitor.lastEvaluated" class="text-xs text-fg-2" :title="formatGovernStamp(monitor.lastEvaluated)">
                  {{ formatGovernRelative(monitor.lastEvaluated) }}
                </span>
                <span v-else class="text-xs text-warn">Not evaluated</span>
              </td>
              <td>
                <GovernMonitorStatusChip :status="monitor.status" />
                <p
                  v-if="monitor.reason"
                  class="mt-1 max-w-28 truncate text-[0.625rem] leading-4"
                  :class="monitor.status === 'no_data' ? 'text-warn' : 'text-fg-3'"
                  :title="monitor.reason"
                >
                  {{ monitor.reason }}
                </p>
              </td>
              <td>
                <NuxtLink v-if="monitor.signalId" :to="`/drift/signals/${encodeURIComponent(monitor.signalId)}`" class="ix-link text-xs">
                  {{ monitor.signalId }}
                </NuxtLink>
                <span v-else class="text-[0.6875rem] text-fg-3">None open</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <footer class="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line-subtle bg-canvas/30 px-4 py-1.5 text-[0.6875rem] leading-4 text-fg-3">
        <span>Firing opens a signal. Muted monitors keep evaluating; No data means nothing was evaluated.</span>
        <span class="ml-auto font-mono">{{ filtered.length }} monitors</span>
      </footer>
    </div>

    <GovernPeekSheet
      :open="peekOpen"
      :title="peekMonitor?.metric ?? 'Monitor'"
      :description="peekMonitor ? `${peekMonitor.description} Applies to ${peekMonitor.appliesTo.join(', ')}.` : undefined"
      :href="peekSignalHref"
      href-label="Open signal"
      @update:open="peekOpen = $event"
    >
      <div v-if="peekMonitor" class="flex flex-col gap-3">
        <dl class="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line-subtle bg-line-subtle">
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.625rem] text-fg-3">Rule</dt>
            <dd class="mt-0.5 font-mono text-[0.6875rem] text-fg-2">{{ peekMonitor.rule }}</dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.625rem] text-fg-3">Severity</dt>
            <dd class="mt-1"><GovernSeverityChip :severity="peekMonitor.severity" /></dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.625rem] text-fg-3">Notifies</dt>
            <dd class="mt-0.5 text-xs text-fg-2">{{ peekMonitor.notifies ?? "No one" }}</dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.625rem] text-fg-3">Last evaluated</dt>
            <dd class="mt-0.5 text-xs text-fg-2">{{ peekMonitor.lastEvaluated ? formatGovernStamp(peekMonitor.lastEvaluated) : "Not evaluated" }}</dd>
          </div>
        </dl>

        <div class="overflow-hidden rounded-lg border border-line-subtle">
          <div class="flex items-center justify-between border-b border-line-subtle px-3 py-2">
            <h3 class="text-xs font-semibold text-fg-1">Evaluations</h3>
            <span class="font-mono text-[0.625rem] text-fg-3">{{ peekMonitor.evaluations.length }}</span>
          </div>
          <table v-if="peekMonitor.evaluations.length" class="ix-agent-table" aria-label="Monitor evaluations">
            <thead>
              <tr>
                <th scope="col">Time</th>
                <th scope="col" class="text-right">Value</th>
                <th scope="col">Result</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="entry in peekMonitor.evaluations" :key="entry.at">
                <td>
                  <span class="text-xs text-fg-2" :title="formatGovernStamp(entry.at)">{{ formatGovernRelative(entry.at) }}</span>
                  <p class="mt-0.5 text-[0.625rem] leading-4 text-fg-3">{{ entry.note }}</p>
                </td>
                <td class="text-right font-mono text-xs text-fg-2">{{ driftMonitorValue(peekMonitor, entry.value) }}</td>
                <td><GovernMonitorStatusChip :status="entry.result" /></td>
              </tr>
            </tbody>
          </table>
          <p v-else class="px-3 py-4 text-xs leading-5 text-fg-3">
            No evaluation is recorded for this monitor. {{ peekMonitor.reason ?? "The monitor did not run in the recorded window." }}
          </p>
        </div>

        <div class="flex flex-wrap gap-2">
          <GovernLockedAction label="Mute monitor" :icon="Gauge" size="sm" />
          <GovernLockedAction label="Edit monitor" :icon="Plus" size="sm" />
        </div>
        <p class="text-[0.625rem] leading-4 text-fg-3">
          Values are recorded preview data. This console does not execute a monitor or change its rule.
        </p>
      </div>
    </GovernPeekSheet>


    <GovernShortcutsDialog v-model:open="helpOpen" :groups="shortcutGroups" />
  </div>
</template>
