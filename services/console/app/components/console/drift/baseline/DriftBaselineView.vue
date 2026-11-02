<script setup lang="ts">
import { computed, ref } from "vue"
import { ArrowLeft, ExternalLink, Gauge, Lock, RefreshCw } from "@lucide/vue"
import GovernAboutPopover from "@/components/console/govern/primitives/GovernAboutPopover.vue"
import GovernDataSourceChip from "@/components/console/govern/primitives/GovernDataSourceChip.vue"
import GovernEvidenceChip from "@/components/console/govern/primitives/GovernEvidenceChip.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import GovernSeverityChip from "@/components/console/govern/primitives/GovernSeverityChip.vue"
import GovernStateChip from "@/components/console/govern/primitives/GovernStateChip.vue"
import GovernMonitorStatusChip from "@/components/console/drift/GovernMonitorStatusChip.vue"
import { formatGovernDate, formatGovernRelative, formatGovernStamp, GOVERN_NOW } from "@/lib/govern-format"
import {
  driftBaselineAge,
  driftBaselineTone,
  driftMonitorsForAgent,
  driftSignalsForBaseline,
  formatDriftValue,
  type DriftBaseline,
} from "@/lib/drift-preview"
import { driftBaselineListHref, driftMonitorListHref, driftSignalHref } from "@/lib/govern-query"

const props = defineProps<{ baseline: DriftBaseline }>()

const about = ref<InstanceType<typeof GovernAboutPopover> | null>(null)

const age = computed(() => driftBaselineAge(props.baseline))
const tone = computed(() => driftBaselineTone(props.baseline))
const openSignals = computed(() => driftSignalsForBaseline(props.baseline.id))
const monitors = computed(() => driftMonitorsForAgent(props.baseline.agent))
const signalByMetric = computed(() => new Map(openSignals.value.map((signal) => [signal.metric, signal])))

const ageLabel = computed(() => {
  if (age.value === null) return "Age not recorded"
  return `${age.value} ${age.value === 1 ? "day" : "days"} since certification`
})

const ageClass = computed(() => {
  if (tone.value === "critical") return "border-transparent bg-transparent text-crit"
  if (tone.value === "warning") return "border-transparent bg-transparent text-warn"
  return "border-line-subtle bg-surface-1 text-fg-3"
})

const summary = computed(() => {
  const baseline = props.baseline
  return `${baseline.agent.name} ${baseline.agent.version} was certified by ${baseline.certifiedBy} on ${formatGovernDate(baseline.certifiedAt)}, from ${baseline.runs} runs recorded between ${formatGovernDate(baseline.windowFrom)} and ${formatGovernDate(baseline.windowTo)}.`
})

const history = computed(() =>
  [...props.baseline.history].sort((left, right) => Date.parse(right.at) - Date.parse(left.at)),
)

function runHref(runId: string): string {
  return `/explore/r/${encodeURIComponent(runId)}`
}

function signalHrefFor(metricName: string): string {
  const signal = signalByMetric.value.get(metricName)
  return signal ? driftSignalHref(signal.id) : ""
}
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">

    <header class="flex flex-col gap-3">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <NuxtLink
            :to="driftBaselineListHref({ agent: 'all', age: 'all' })"
            class="inline-flex items-center gap-1.5 rounded text-xs text-fg-3 transition-colors hover:text-fg-1"
          >
            <ArrowLeft :size="13" :stroke-width="1.9" aria-hidden="true" />
            Back to baselines
          </NuxtLink>
          <div class="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
            <h1 class="ix-page-title text-fg-1">{{ baseline.agent.name }}</h1>
            <span class="rounded border border-line-subtle bg-surface-1 px-1.5 py-0.5 font-mono text-[0.6875rem] text-fg-2">{{ baseline.agent.version }}</span>
            <GovernEvidenceChip :evidence="baseline.evidence" />
            <span class="inline-flex h-5.5 items-center rounded-full border px-2 text-xs leading-none font-medium" :class="ageClass">{{ ageLabel }}</span>
                      </div>
          <p class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-fg-3">
            <span class="font-mono">{{ baseline.id }}</span>
            <span aria-hidden="true">·</span>
            <span class="font-mono">{{ baseline.agent.id }}</span>
          </p>
          <p class="mt-2 max-w-3xl text-sm leading-6 text-fg-2">{{ summary }}</p>
        </div>

        <div class="flex shrink-0 flex-wrap items-center gap-2">
          <GovernDataSourceChip @open="about?.open()" />
    <GovernAboutPopover
      ref="about"
      verdict="Every value on this page is an illustrative fixture. No baseline read model is connected to this console."
      contract="operator.drift.baselines.v1"
      scope="org_demo_42 · workspace ws_42"
      range="Certified 12 Sep 2026"
      coverage="Preview fixtures · no baseline read model connected"
      phase="D5 · Phase B2"
      claim="No enforcement, audit, or billing claim."
      :notes="[
        { lead: 'A baseline is a certified window, not a live average.', body: 'The band is fixed when a person certifies it. New runs do not move it, and this console cannot re-certify it.' },
        { lead: 'A missing baseline is stated, never guessed.', body: 'An agent version with no recorded baseline is not evaluated for drift, and the console does not substitute a default band.' },
      ]"
    />
          <GovernLockedAction label="Re-baseline" :icon="RefreshCw" />
        </div>
      </div>

      <p class="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[0.6875rem] leading-4 text-fg-3">
        <Lock :size="11" :stroke-width="1.8" aria-hidden="true" />
        A baseline is fixed at certification. This console never moves the band or re-certifies it.
      </p>
    </header>

    <div class="grid gap-3 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <div class="flex flex-col gap-3">
        <section class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
          <header class="flex flex-wrap items-center justify-between gap-2 border-b border-line-subtle px-4 py-2.5">
            <h2 class="text-sm font-semibold text-fg-1">Certified metrics</h2>
            <span class="font-mono text-[0.6875rem] text-fg-3">{{ baseline.metrics.length }} metrics</span>
          </header>
          <div class="ix-scroll overflow-x-auto">
            <table class="ix-agent-table" aria-label="Certified metrics">
              <thead>
                <tr>
                  <th scope="col" class="min-w-32">Metric</th>
                  <th scope="col" class="w-28 text-right">Baseline</th>
                  <th scope="col" class="min-w-32 text-right">Band</th>
                  <th scope="col" class="w-28">Signal</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="metric in baseline.metrics" :key="metric.name">
                  <td class="text-xs font-medium text-fg-1">{{ metric.name }}</td>
                  <td class="text-right font-mono text-xs whitespace-nowrap text-fg-2">{{ formatDriftValue(metric.baseline, metric.unit) }}</td>
                  <td class="text-right font-mono text-[0.6875rem] text-fg-3">
                    {{ formatDriftValue(metric.low, metric.unit) }} – {{ formatDriftValue(metric.high, metric.unit) }}
                  </td>
                  <td>
                    <NuxtLink
                      v-if="signalHrefFor(metric.name)"
                      :to="signalHrefFor(metric.name)"
                      class="ix-link text-xs"
                    >
                      View signal
                    </NuxtLink>
                    <span v-else class="text-[0.6875rem] text-fg-3">Inside band</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <footer class="border-t border-line-subtle bg-canvas/30 px-4 py-1.5 text-[0.6875rem] leading-4 text-fg-3">
            The band is the certified low–high range. A signal is only listed when it is open or acknowledged.
          </footer>
        </section>

        <section class="rounded-lg border border-line-subtle bg-surface-1">
          <header class="flex flex-wrap items-center justify-between gap-2 border-b border-line-subtle px-4 py-2.5">
            <h2 class="text-sm font-semibold text-fg-1">Sample runs</h2>
            <span class="font-mono text-[0.6875rem] text-fg-3">{{ baseline.sampleRuns.length }} cited</span>
          </header>
          <div class="flex flex-wrap gap-2 px-4 py-3">
            <NuxtLink
              v-for="runId in baseline.sampleRuns"
              :key="runId"
              :to="runHref(runId)"
              class="inline-flex h-7 items-center gap-1.5 rounded-md border border-line-subtle bg-surface-2 px-2 font-mono text-[0.6875rem] text-fg-2 transition-colors hover:border-line hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            >
              {{ runId }}
              <ExternalLink :size="10" :stroke-width="1.9" aria-hidden="true" />
            </NuxtLink>
            <p v-if="!baseline.sampleRuns.length" class="text-xs text-fg-3">No sample run is recorded.</p>
          </div>
          <p class="border-t border-line-subtle px-4 py-1.5 text-[0.6875rem] leading-4 text-fg-3">
            These are the runs the baseline cites, not every run in the window.
          </p>
        </section>

        <section class="rounded-lg border border-line-subtle bg-surface-1">
          <header class="border-b border-line-subtle px-4 py-2.5">
            <h2 class="text-sm font-semibold text-fg-1">Re-baseline history</h2>
            <p class="mt-0.5 text-[0.6875rem] leading-4 text-fg-3">Newest first. Each entry records who certified it and why.</p>
          </header>
          <ol class="divide-y divide-line-subtle">
            <li v-for="entry in history" :key="entry.id" class="px-4 py-3">
              <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <p class="text-xs font-medium text-fg-1">{{ entry.by }}</p>
                <span class="font-mono text-[0.625rem] text-fg-3" :title="formatGovernStamp(entry.at)">{{ formatGovernDate(entry.at) }}</span>
              </div>
              <p class="mt-1 text-[0.6875rem] leading-5 text-fg-2">{{ entry.why }}</p>
            </li>
            <li v-if="!history.length" class="px-4 py-4 text-xs text-fg-3">No re-baseline is recorded.</li>
          </ol>
        </section>
      </div>

      <div class="flex flex-col gap-3">
        <section class="rounded-lg border border-line-subtle bg-surface-1">
          <header class="flex items-center justify-between border-b border-line-subtle px-4 py-2.5">
            <h2 class="text-sm font-semibold text-fg-1">Open signals</h2>
            <span class="font-mono text-[0.6875rem] text-fg-3">{{ openSignals.length }}</span>
          </header>
          <ul v-if="openSignals.length" class="divide-y divide-line-subtle">
            <li v-for="signal in openSignals" :key="signal.id" class="px-4 py-3">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <NuxtLink :to="driftSignalHref(signal.id)" class="text-xs font-medium text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline">
                  {{ signal.metric }}
                </NuxtLink>
                <span class="flex items-center gap-1.5">
                  <GovernSeverityChip :severity="signal.severity" />
                  <GovernStateChip :state="signal.state" />
                </span>
              </div>
              <p class="mt-1 text-[0.625rem] text-fg-3">Opened {{ formatGovernRelative(signal.openedAt, GOVERN_NOW) }} · {{ signal.owner ?? "No owner" }}</p>
            </li>
          </ul>
          <p v-else class="px-4 py-4 text-xs leading-5 text-fg-3">No signal from this baseline is open or acknowledged.</p>
        </section>

        <section class="rounded-lg border border-line-subtle bg-surface-1">
          <header class="flex flex-wrap items-center justify-between gap-2 border-b border-line-subtle px-4 py-2.5">
            <h2 class="text-sm font-semibold text-fg-1">Monitors</h2>
            <NuxtLink :to="driftMonitorListHref({ status: 'all', agent: baseline.agent.id })" class="text-xs text-fg-2 underline-offset-2 hover:text-fg-1 hover:underline">
              All monitors
            </NuxtLink>
          </header>
          <ul v-if="monitors.length" class="divide-y divide-line-subtle">
            <li v-for="monitor in monitors" :key="monitor.id" class="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5">
              <div class="min-w-0">
                <p class="flex items-center gap-1.5 text-xs font-medium text-fg-1">
                  <Gauge :size="12" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
                  {{ monitor.metric }}
                </p>
                <p class="mt-0.5 font-mono text-[0.625rem] text-fg-3">{{ monitor.rule }}</p>
              </div>
              <GovernMonitorStatusChip class="shrink-0" :status="monitor.status" />
            </li>
          </ul>
          <p v-else class="px-4 py-4 text-xs text-fg-3">No monitor applies to this agent version.</p>
          <p v-if="monitors.length" class="border-t border-line-subtle px-4 py-1.5 text-[0.6875rem] leading-4 text-fg-3">
            Last evaluated {{ formatGovernRelative(monitors[0]?.lastEvaluated, GOVERN_NOW) }}.
          </p>
        </section>

        <section class="rounded-lg border border-line-subtle bg-surface-1">
          <h2 class="border-b border-line-subtle px-4 py-2.5 text-sm font-semibold text-fg-1">What the baseline does not cover</h2>
          <div class="px-4 py-3 text-[0.6875rem] leading-5 text-fg-3">
            <p>
              The baseline certifies only the metrics listed above. Behaviour outside those metrics is not compared,
              and the console does not infer it.
            </p>
          </div>
        </section>
      </div>
    </div>


    <p v-if="!monitors.length" class="flex items-center gap-1.5 text-[0.6875rem] leading-4 text-fg-3">
      <Lock :size="11" :stroke-width="1.8" aria-hidden="true" />
      No monitor means no automatic detection for this agent version.
    </p>
  </div>
</template>
