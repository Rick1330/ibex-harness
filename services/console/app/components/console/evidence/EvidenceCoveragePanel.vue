<script setup lang="ts">
import { computed } from "vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import { formatGovernNumber, formatGovernPercent, formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"
import {
  COMPLETENESS_LABELS,
  COMPLETENESS_MEANING,
  COMPLETENESS_ORDER,
  COMPLETENESS_TONE,
  completenessTotal,
  type OperatorEvidenceSummary,
} from "@/lib/evidence-summary"

const props = defineProps<{ summary: OperatorEvidenceSummary }>()

const incomplete = computed(() => Math.max(0, props.summary.runs_total - props.summary.capture_complete_runs))
const completePercent = computed(() =>
  props.summary.runs_total === 0 ? 0 : (props.summary.capture_complete_runs / props.summary.runs_total) * 100,
)
const counted = computed(() => completenessTotal(props.summary.completeness))
const policyMode = computed(() => props.summary.capture_policy.mode ?? "Deployment default")
const policyScope = computed(() => {
  const policy = props.summary.capture_policy
  if (policy.scope === null) return "No organization policy row"
  return policy.scope === "agent" ? "Highest-priority agent override" : "Organization-wide"
})
const holdText = computed(() => {
  const hold = props.summary.legal_hold
  if (!hold.active) return "None active"
  return hold.since ? `Active since ${formatGovernStamp(hold.since)}` : "Active"
})

function tierPercent(key: (typeof COMPLETENESS_ORDER)[number]): number {
  if (props.summary.runs_total === 0) return 0
  return (props.summary.completeness[key] / props.summary.runs_total) * 100
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4">
      <GovernStatTile
        label="Runs in window"
        :value="formatGovernNumber(summary.runs_total)"
        helper="One row per captured run"
      />
      <GovernStatTile
        label="Complete capture"
        :value="formatGovernNumber(summary.capture_complete_runs)"
        :helper="`${formatGovernPercent(completePercent, 1)} of the window`"
        tone="success"
      />
      <GovernStatTile
        label="Not complete"
        :value="formatGovernNumber(incomplete)"
        helper="Partial, sampled, late, redacted, expired, deleted, or simulated"
        :tone="incomplete > 0 ? 'warning' : 'default'"
      />
      <GovernStatTile
        label="Last run captured"
        :value="summary.last_run_at ? formatGovernRelative(summary.last_run_at) : 'None in window'"
        :helper="summary.last_run_at ? formatGovernStamp(summary.last_run_at) : 'No run was recorded for this range'"
      />
    </div>

    <GovernCaveat v-if="counted !== summary.runs_total" tone="warning" title="Counts do not reconcile">
      {{ formatGovernNumber(counted) }} rows are counted by completeness but {{ formatGovernNumber(summary.runs_total) }}
      were reported. Treat the coverage figures as partial until the contract and the schema agree.
    </GovernCaveat>

    <div class="console-panel p-3">
      <div
        class="flex h-2 w-full overflow-hidden rounded-full bg-raised"
        role="img"
        :aria-label="`Capture completeness across ${formatGovernNumber(summary.runs_total)} runs`"
      >
        <span
          v-for="key in COMPLETENESS_ORDER"
          :key="key"
          :style="{ width: `${tierPercent(key)}%` }"
          :class="{
            'bg-ok': COMPLETENESS_TONE[key] === 'success',
            'bg-warn': COMPLETENESS_TONE[key] === 'warning',
            'bg-fg-3': COMPLETENESS_TONE[key] === 'default',
          }"
        />
      </div>
      <ul class="mt-2 flex flex-col gap-1 text-[0.6875rem] leading-4 text-fg-3">
        <li v-for="key in COMPLETENESS_ORDER" :key="key" class="flex flex-wrap items-baseline gap-x-2">
          <span class="w-20 shrink-0 font-medium text-fg-2">{{ COMPLETENESS_LABELS[key] }}</span>
          <span class="font-mono tabular-nums text-fg-1">{{ formatGovernNumber(summary.completeness[key]) }}</span>
          <span class="font-mono tabular-nums">{{ formatGovernPercent(tierPercent(key), 1) }}</span>
          <span class="min-w-0 flex-1">{{ COMPLETENESS_MEANING[key] }}</span>
        </li>
      </ul>
    </div>

    <div class="grid gap-2 sm:grid-cols-3">
      <GovernStatTile label="Capture policy" :value="policyMode" :helper="policyScope" />
      <GovernStatTile
        label="Agent overrides"
        :value="formatGovernNumber(summary.capture_policy.agent_overrides)"
        helper="Policies that apply to one agent"
      />
      <GovernStatTile
        label="Legal hold"
        :value="summary.legal_hold.active ? 'Active' : 'None'"
        :helper="holdText"
        :tone="summary.legal_hold.active ? 'warning' : 'default'"
      />
    </div>

    <GovernCaveat tone="info" title="What complete capture does not claim">
      It names the record, not the delivery: this page reports relay health separately because the outbox carries no run
      reference. It is also not a population estimate — a sampled or partial window is reported as sampled or partial,
      never extrapolated.
    </GovernCaveat>
  </div>
</template>
