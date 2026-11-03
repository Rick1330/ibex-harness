<script setup lang="ts">
import { computed, ref } from "vue"
import { Apple, ArrowLeft, ExternalLink, Lock, ShieldAlert, UserRound } from "@lucide/vue"
import GovernAboutPopover from "@/components/console/govern/primitives/GovernAboutPopover.vue"
import GovernBandChart from "@/components/console/govern/primitives/GovernBandChart.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernDataSourceChip from "@/components/console/govern/primitives/GovernDataSourceChip.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import GovernPendingData from "@/components/console/govern/primitives/GovernPendingData.vue"
import GovernSeverityChip from "@/components/console/govern/primitives/GovernSeverityChip.vue"
import GovernShortcutsDialog from "@/components/console/govern/primitives/GovernShortcutsDialog.vue"
import GovernStateChip from "@/components/console/govern/primitives/GovernStateChip.vue"
import GovernTabBar from "@/components/console/govern/primitives/GovernTabBar.vue"
import { useGovernShortcuts } from "@/composables/useGovernShortcuts"
import { formatGovernStamp } from "@/lib/govern-format"
import { driftBaselineHref, driftListHref, driftSignalHref, DRIFT_LIST_DEFAULT, type DriftSignalTab } from "@/lib/govern-query"
import {
  DRIFT_STATE_DEFINITIONS,
  driftBaselineById,
  driftChange,
  driftMarkerValues,
  driftMonitorById,
  driftSummarySentence,
  driftSuspectedCauses,
  formatDriftValue,
  type DriftRun,
  type DriftSignal,
} from "@/lib/drift-preview"

const props = defineProps<{
  signal: DriftSignal
  state: { tab: DriftSignalTab }
}>()

const emit = defineEmits<{ update: [state: { tab: DriftSignalTab }] }>()

const about = ref<InstanceType<typeof GovernAboutPopover> | null>(null)
const change = computed(() => driftChange(props.signal))
const summary = computed(() => driftSummarySentence(props.signal))
const baseline = computed(() => driftBaselineById(props.signal.baselineId))
const monitor = computed(() => driftMonitorById(props.signal.monitorId))
const causes = computed(() => driftSuspectedCauses(props.signal))
const markers = computed(() => driftMarkerValues(props.signal))

const tabs = computed(() => [
  { id: "overview", label: "Overview" },
  { id: "runs", label: `Runs (${props.signal.runsOutside.length + props.signal.runsInside.length})` },
  { id: "compare", label: "Compare" },
  { id: "activity", label: `Activity (${props.signal.activity.length})` },
])

const activity = computed(() => [...props.signal.activity].sort((left, right) => Date.parse(right.at) - Date.parse(left.at)))

function selectTab(id: string): void {
  emit("update", { tab: id as DriftSignalTab })
}

function runHref(runId: string): string {
  return `/explore/r/${encodeURIComponent(runId)}`
}

function kindLabel(kind: string): string {
  if (kind === "state") return "State change"
  if (kind === "owner") return "Owner"
  if (kind === "notification") return "Notification"
  if (kind === "cause") return "Recorded cause"
  if (kind === "note") return "Note"
  return "Opened"
}

function runValue(run: DriftRun): string {
  return formatDriftValue(run.value, props.signal.unit)
}

function copyCurrentLink(): void {
  if (!import.meta.client) return
  void navigator.clipboard.writeText(`${window.location.origin}${driftSignalHref(props.signal.id, props.state)}`)
}

const { helpOpen } = useGovernShortcuts({ keys: { y: copyCurrentLink } })

const shortcutGroups = [
  {
    title: "This page",
    rows: [
      { keys: "1–4", label: "Switch tab" },
      { keys: "y", label: "Copy link to this signal" },
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
            <h1 class="ix-page-title text-fg-1">{{ signal.metric }}</h1>
            <GovernSeverityChip :severity="signal.severity" />
            <GovernStateChip :state="signal.state" />
                      </div>
          <p class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-fg-3">
            <span>{{ signal.agent.name }} · {{ signal.agent.version }}</span>
            <span aria-hidden="true">·</span>
            <span class="font-mono">{{ signal.id }}</span>
            <GovernCopyId :id="signal.id" label="Signal ID" icon-only />
          </p>
          <p class="mt-2 max-w-3xl text-sm leading-6 text-fg-2">{{ summary }}</p>
        </div>

        <div class="flex shrink-0 flex-wrap items-center gap-2">
          <GovernDataSourceChip @open="about?.open()" />
    <GovernAboutPopover
      ref="about"
      verdict="Every value on this page is an illustrative fixture. No drift read model is connected to this console."
      contract="operator.drift.alerts.v1"
      scope="org_demo_42 · workspace ws_42"
      range="Signal recorded 21–26 Oct 2026"
      coverage="Preview fixtures · no drift read model connected"
      phase="D5 · Phase B2"
      claim="No enforcement, audit, or billing claim."
      :notes="[
        { lead: 'The band is certified, the observation is not.', body: 'The baseline and tolerance come from a certified window. The observed series is a replay fixture, so the chart is marked Illustrative.' },
        { lead: 'No evaluation runs in this console.', body: 'This page does not compute drift. It renders recorded values and never fills a missing evaluation with a passing value.' },
      ]"
    />
          <GovernLockedAction label="Acknowledge" :icon="UserRound" />
          <GovernLockedAction label="Snooze" :icon="Apple" />
        </div>
      </div>

      <p class="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[0.6875rem] leading-4 text-fg-3">
        <Lock :size="11" :stroke-width="1.8" aria-hidden="true" />
        {{ DRIFT_STATE_DEFINITIONS[signal.state] }}
      </p>
    </header>

    <GovernTabBar :tabs="tabs" :model-value="state.tab" aria-label="Signal views" @update:model-value="selectTab" />

    <template v-if="state.tab === 'overview'">
      <GovernBandChart
        :points="signal.series"
        :threshold="signal.threshold"
        :unit="signal.unit"
        :label="`${signal.metric} for ${signal.agent.name} ${signal.agent.version}`"
        :markers="markers"
        :summary="summary"
        illustrative
      />

      <div class="grid gap-3 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <div class="flex flex-col gap-3">
          <section class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
            <h2 class="border-b border-line-subtle px-4 py-2.5 text-sm font-semibold text-fg-1">Facts</h2>
            <dl class="grid grid-cols-2 gap-px bg-line-subtle sm:grid-cols-3">
              <div class="bg-surface-1 px-4 py-2.5">
                <dt class="text-[0.6875rem] text-fg-3">Observed</dt>
                <dd class="mt-0.5 font-mono text-sm font-medium text-fg-1">{{ formatDriftValue(signal.observed, signal.unit) }}</dd>
              </div>
              <div class="bg-surface-1 px-4 py-2.5">
                <dt class="text-[0.6875rem] text-fg-3">Certified baseline</dt>
                <dd class="mt-0.5 font-mono text-sm text-fg-2">{{ formatDriftValue(signal.baseline, signal.unit) }}</dd>
              </div>
              <div class="bg-surface-1 px-4 py-2.5">
                <dt class="text-[0.6875rem] text-fg-3">Change</dt>
                <dd class="mt-0.5 font-mono text-sm font-medium text-fg-1">{{ change.label }}</dd>
              </div>
              <div class="bg-surface-1 px-4 py-2.5">
                <dt class="text-[0.6875rem] text-fg-3">Band</dt>
                <dd class="mt-0.5 font-mono text-xs text-fg-2">
                  {{ formatDriftValue(signal.baseline - signal.tolerance, signal.unit) }} –
                  {{ formatDriftValue(signal.baseline + signal.tolerance, signal.unit) }}
                </dd>
              </div>
              <div class="bg-surface-1 px-4 py-2.5">
                <dt class="text-[0.6875rem] text-fg-3">Threshold</dt>
                <dd class="mt-0.5 font-mono text-xs text-fg-2">{{ formatDriftValue(signal.threshold, signal.unit) }}</dd>
              </div>
              <div class="bg-surface-1 px-4 py-2.5">
                <dt class="text-[0.6875rem] text-fg-3">Evaluation window</dt>
                <dd class="mt-0.5 text-xs text-fg-2">{{ signal.windowHours }}h rolling</dd>
              </div>
              <div class="bg-surface-1 px-4 py-2.5">
                <dt class="text-[0.6875rem] text-fg-3">First seen</dt>
                <dd class="mt-0.5 text-xs text-fg-2">{{ formatGovernStamp(signal.firstSeen) }}</dd>
              </div>
              <div class="bg-surface-1 px-4 py-2.5">
                <dt class="text-[0.6875rem] text-fg-3">Time to detect</dt>
                <dd class="mt-0.5 text-xs text-fg-2">{{ signal.timeToDetectHours }}h</dd>
              </div>
              <div class="bg-surface-1 px-4 py-2.5">
                <dt class="text-[0.6875rem] text-fg-3">Owner</dt>
                <dd class="mt-0.5 text-xs" :class="signal.owner ? 'text-fg-1' : 'text-warn'">{{ signal.owner ?? "No owner" }}</dd>
              </div>
              <div class="bg-surface-1 px-4 py-2.5">
                <dt class="text-[0.6875rem] text-fg-3">Monitor</dt>
                <dd class="mt-0.5 font-mono text-xs text-fg-2">{{ signal.monitorId }}</dd>
                <dd v-if="monitor" class="mt-0.5 text-[0.625rem] text-fg-3">{{ monitor.metric }} · {{ monitor.status === "firing" ? "Firing" : monitor.status === "ok" ? "OK" : monitor.status === "muted" ? "Muted" : "No data" }}</dd>
              </div>
              <div class="bg-surface-1 px-4 py-2.5">
                <dt class="text-[0.6875rem] text-fg-3">Baseline</dt>
                <dd class="mt-0.5 text-xs">
                  <NuxtLink v-if="baseline" :to="driftBaselineHref(baseline.agent.id)" class="ix-link font-mono text-xs">
                    {{ baseline.id }}
                  </NuxtLink>
                  <span v-else class="text-fg-3">Not recorded</span>
                </dd>
              </div>
              <div class="bg-surface-1 px-4 py-2.5">
                <dt class="text-[0.6875rem] text-fg-3">What it measures</dt>
                <dd class="mt-0.5 text-xs leading-5 text-fg-2">{{ signal.description }}</dd>
              </div>
            </dl>
          </section>

          <section class="rounded-lg border border-line-subtle bg-surface-1">
            <div class="flex flex-wrap items-center justify-between gap-2 border-b border-line-subtle px-4 py-2.5">
              <h2 class="text-sm font-semibold text-fg-1">Runs outside and inside the band</h2>
              <button type="button" class="text-xs text-fg-2 underline underline-offset-2 hover:text-fg-1" @click="selectTab('runs')">
                View all runs
              </button>
            </div>
            <div class="grid gap-px bg-line-subtle sm:grid-cols-2">
              <div class="bg-surface-1">
                <p class="px-4 pt-2.5 text-[0.6875rem] font-medium tracking-wide text-crit uppercase">Outside the band</p>
                <table class="ix-agent-table" aria-label="Runs outside the band">
                  <thead>
                    <tr>
                      <th scope="col">Run</th>
                      <th scope="col" class="w-20 text-right">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="run in signal.runsOutside.slice(0, 3)" :key="run.runId">
                      <td>
                        <NuxtLink :to="runHref(run.runId)" class="font-mono text-xs text-fg-1 hover:text-accent-memory">{{ run.runId }}</NuxtLink>
                        <span class="mt-0.5 block text-[0.625rem] text-fg-3">{{ formatGovernStamp(run.at) }}</span>
                      </td>
                      <td class="text-right font-mono text-xs text-fg-2">{{ runValue(run) }}</td>
                    </tr>
                    <tr v-if="!signal.runsOutside.length">
                      <td colspan="2" class="text-xs text-fg-3">No run outside the band is recorded.</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="bg-surface-1">
                <p class="px-4 pt-2.5 text-[0.6875rem] font-medium tracking-wide text-ok uppercase">Inside the band</p>
                <table class="ix-agent-table" aria-label="Runs inside the band">
                  <thead>
                    <tr>
                      <th scope="col">Run</th>
                      <th scope="col" class="w-20 text-right">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="run in signal.runsInside.slice(0, 3)" :key="run.runId">
                      <td>
                        <NuxtLink :to="runHref(run.runId)" class="font-mono text-xs text-fg-1 hover:text-accent-memory">{{ run.runId }}</NuxtLink>
                        <span class="mt-0.5 block text-[0.625rem] text-fg-3">{{ formatGovernStamp(run.at) }}</span>
                      </td>
                      <td class="text-right font-mono text-xs text-fg-2">{{ runValue(run) }}</td>
                    </tr>
                    <tr v-if="!signal.runsInside.length">
                      <td colspan="2" class="text-xs text-fg-3">No run inside the band is recorded.</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        </div>

        <div class="flex flex-col gap-3">
          <section class="rounded-lg border border-line-subtle bg-surface-1">
            <div class="border-b border-line-subtle px-4 py-2.5">
              <h2 class="text-sm font-semibold text-fg-1">Suspected causes</h2>
              <p class="mt-0.5 text-[0.6875rem] leading-4 text-fg-3">
                Recorded changes in the 72 hours before the first out-of-band point. Ranked nearest first; none is proven.
              </p>
            </div>
            <ol v-if="causes.length" class="divide-y divide-line-subtle">
              <li v-for="entry in causes" :key="entry.cause.id" class="px-4 py-3">
                <div class="flex flex-wrap items-baseline justify-between gap-2">
                  <span class="text-[0.6875rem] font-medium text-fg-3">{{ entry.label }}</span>
                  <span class="font-mono text-[0.625rem] text-fg-3">{{ formatGovernStamp(entry.cause.at) }}</span>
                </div>
                <NuxtLink :to="entry.cause.href" class="mt-1 block text-xs font-medium text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline">
                  {{ entry.cause.title }}
                </NuxtLink>
                <p class="mt-1 text-[0.6875rem] leading-4 text-fg-3">{{ entry.cause.detail }}</p>
              </li>
            </ol>
            <p v-else class="px-4 py-4 text-xs leading-5 text-fg-3">
              No recorded change falls in the 72 hours before the first out-of-band point.
            </p>
          </section>

          <section class="rounded-lg border border-line-subtle bg-surface-1">
            <h2 class="border-b border-line-subtle px-4 py-2.5 text-sm font-semibold text-fg-1">Next steps</h2>
            <ol class="divide-y divide-line-subtle text-xs leading-5 text-fg-2">
              <li class="flex gap-2 px-4 py-2.5">
                <span class="font-mono text-[0.625rem] text-fg-3">1</span>
                <span>
                  Assign an owner. Acknowledging and snoozing need the drift write contract, so this console shows them locked.
                </span>
              </li>
              <li v-if="causes[0]" class="flex gap-2 px-4 py-2.5">
                <span class="font-mono text-[0.625rem] text-fg-3">2</span>
                <span>
                  Review the nearest recorded change:
                  <NuxtLink :to="causes[0].cause.href" class="ix-link">{{ causes[0].cause.title }}</NuxtLink>
                </span>
              </li>
              <li class="flex gap-2 px-4 py-2.5">
                <span class="font-mono text-[0.625rem] text-fg-3">{{ causes[0] ? 3 : 2 }}</span>
                <span>
                  If the new behaviour is intended, re-baseline. The baseline must be re-certified; this console cannot change it.
                </span>
              </li>
            </ol>
          </section>
        </div>
      </div>
    </template>

    <template v-else-if="state.tab === 'runs'">
      <div class="grid gap-3 xl:grid-cols-2">
        <section class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
          <header class="flex items-center justify-between border-b border-line-subtle px-4 py-2.5">
            <h2 class="text-sm font-semibold text-fg-1">Outside the band</h2>
            <span class="font-mono text-[0.6875rem] text-fg-3">{{ signal.runsOutside.length }} runs</span>
          </header>
          <table class="ix-agent-table" aria-label="Runs outside the band">
            <thead>
              <tr>
                <th scope="col">Run</th>
                <th scope="col">Time</th>
                <th scope="col" class="text-right">Value</th>
                <th scope="col" class="text-right">Duration</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="run in signal.runsOutside" :key="run.runId">
                <td><NuxtLink :to="runHref(run.runId)" class="font-mono text-xs text-fg-1 hover:text-accent-memory">{{ run.runId }}</NuxtLink></td>
                <td class="text-xs text-fg-2">{{ formatGovernStamp(run.at) }}</td>
                <td class="text-right font-mono text-xs font-medium text-crit">{{ runValue(run) }}</td>
                <td class="text-right font-mono text-xs text-fg-3">{{ run.durationSeconds.toFixed(1) }}s</td>
              </tr>
              <tr v-if="!signal.runsOutside.length">
                <td colspan="4" class="text-xs text-fg-3">No run outside the band is recorded.</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
          <header class="flex items-center justify-between border-b border-line-subtle px-4 py-2.5">
            <h2 class="text-sm font-semibold text-fg-1">Inside the band</h2>
            <span class="font-mono text-[0.6875rem] text-fg-3">{{ signal.runsInside.length }} runs</span>
          </header>
          <table class="ix-agent-table" aria-label="Runs inside the band">
            <thead>
              <tr>
                <th scope="col">Run</th>
                <th scope="col">Time</th>
                <th scope="col" class="text-right">Value</th>
                <th scope="col" class="text-right">Duration</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="run in signal.runsInside" :key="run.runId">
                <td><NuxtLink :to="runHref(run.runId)" class="font-mono text-xs text-fg-1 hover:text-accent-memory">{{ run.runId }}</NuxtLink></td>
                <td class="text-xs text-fg-2">{{ formatGovernStamp(run.at) }}</td>
                <td class="text-right font-mono text-xs font-medium text-ok">{{ runValue(run) }}</td>
                <td class="text-right font-mono text-xs text-fg-3">{{ run.durationSeconds.toFixed(1) }}s</td>
              </tr>
              <tr v-if="!signal.runsInside.length">
                <td colspan="4" class="text-xs text-fg-3">No run inside the band is recorded.</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
      <p class="flex items-center gap-1.5 text-[0.6875rem] leading-4 text-fg-3">
        <ShieldAlert :size="11" :stroke-width="1.8" aria-hidden="true" />
        Runs are the recorded examples attached to this signal, not a sample of every run in the window.
      </p>
    </template>

    <template v-else-if="state.tab === 'compare'">
      <GovernPendingData
        title="Attribute comparison"
        contract="operator.drift.alerts.v1"
        description="Comparing the runs inside and outside the band by tool, model, or prompt needs an attribute breakdown from the drift read model. This console does not infer one."
      />
    </template>

    <template v-else>
      <section class="rounded-lg border border-line-subtle bg-surface-1">
        <header class="border-b border-line-subtle px-4 py-2.5">
          <h2 class="text-sm font-semibold text-fg-1">Activity</h2>
          <p class="mt-0.5 text-[0.6875rem] leading-4 text-fg-3">
            Recorded state changes, ownership, notifications, and linked causes. Newest first.
          </p>
        </header>
        <ol class="px-4 py-1">
          <li v-for="(entry, index) in activity" :key="entry.id" class="relative flex gap-3 py-3">
            <span class="relative flex w-4 shrink-0 justify-center">
              <span v-if="index < activity.length - 1" class="absolute top-4 bottom-[-1.25rem] w-px bg-line-subtle" aria-hidden="true" />
              <span class="mt-1 size-2 rounded-full bg-line-strong" aria-hidden="true" />
            </span>
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <p class="text-xs font-medium text-fg-1">{{ entry.actor }}</p>
                <span class="font-mono text-[0.625rem] text-fg-3">{{ formatGovernStamp(entry.at) }}</span>
              </div>
              <p class="mt-0.5 text-[0.6875rem] text-fg-3">{{ kindLabel(entry.kind) }}</p>
              <p class="mt-1 text-xs leading-5 text-fg-2">{{ entry.text }}</p>
              <NuxtLink
                v-if="entry.eventId"
                :to="`/audit/events/${entry.eventId}`"
                class="mt-1 inline-flex items-center gap-1 font-mono text-[0.625rem] text-fg-3 underline-offset-2 hover:text-fg-1 hover:underline"
              >
                {{ entry.eventId }}
                <ExternalLink :size="10" :stroke-width="1.9" aria-hidden="true" />
              </NuxtLink>
            </div>
          </li>
        </ol>
      </section>
    </template>


    <GovernShortcutsDialog v-model:open="helpOpen" :groups="shortcutGroups" />
  </div>
</template>
