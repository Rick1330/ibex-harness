<script setup lang="ts">
import { computed, ref } from "vue"
import { ArrowUpRight, BadgeCheck, ScanLine } from "@lucide/vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernDecisionPill from "@/components/console/govern/primitives/GovernDecisionPill.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernEmptyValue from "@/components/console/govern/primitives/GovernEmptyValue.vue"
import GovernSparkline from "@/components/console/govern/primitives/GovernSparkline.vue"
import { formatGovernNumber, formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"
import {
  POLICY_DECISION_ORDER,
  policyDecisionLabel,
  policyRuleProvenance,
  policyRuleRuns,
  type PolicyDecisionKind,
  type PolicyRule,
} from "@/lib/policy-preview"
import { policyResolveHref } from "@/lib/govern-query"

const props = defineProps<{
  rule: PolicyRule
  returnTo: string
}>()

type Filter = PolicyDecisionKind | "all"
const filter = ref<Filter>("all")

const all = computed(() =>
  [...policyRuleRuns(props.rule.id)].sort((left, right) => Date.parse(right.at) - Date.parse(left.at)),
)
const rows = computed(() => all.value.filter((run) => filter.value === "all" || run.decision === filter.value))
const counts = computed(() =>
  POLICY_DECISION_ORDER.map((decision) => ({
    decision,
    label: policyDecisionLabel(decision),
    count: all.value.filter((run) => run.decision === decision).length,
  })).filter((entry) => entry.count > 0),
)
const provenance = computed(() => policyRuleProvenance(props.rule.id))

function runHref(runId: string): string {
  return policyResolveHref({ run: runId, at: "" })
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="grid gap-3 rounded-lg border border-line-subtle bg-surface-1 px-4 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
      <div class="min-w-0">
        <p class="text-sm font-medium text-fg-1">
          {{ formatGovernNumber(all.length) }} linked run{{ all.length === 1 ? "" : "s" }} · {{ formatGovernNumber(rule.fired) }} fires in 7 days
        </p>
        <p class="mt-0.5 text-xs text-fg-3">
          {{ provenance.complete }} complete · {{ provenance.partial }} partial provenance
        </p>
      </div>
      <div class="flex items-center gap-2">
        <GovernSparkline :points="rule.firedTrend" :label="`${rule.label} fires per day, last 14 days`" :width="120" :height="28" illustrative />
        <span class="text-[0.625rem] leading-3 text-fg-3">14-day trend<br>illustrative</span>
      </div>
    </div>

    <GovernCaveat v-if="all.length > 0" tone="info">
      These runs are the decisions that joined to this rule. A run without a policy link is absent, not necessarily unaffected.
    </GovernCaveat>

    <div class="flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter runs by decision">
      <button
        type="button"
        class="inline-flex h-7 items-center gap-1 rounded-full border px-2.5 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        :class="filter === 'all' ? 'border-line-strong bg-surface-2 text-fg-1' : 'border-line-subtle bg-surface-1 text-fg-3 hover:text-fg-1'"
        :aria-pressed="filter === 'all'"
        @click="filter = 'all'"
      >
        All <span class="font-mono text-[0.625rem]">{{ all.length }}</span>
      </button>
      <button
        v-for="entry in counts"
        :key="entry.decision"
        type="button"
        class="inline-flex h-7 items-center gap-1 rounded-full border px-2.5 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        :class="filter === entry.decision ? 'border-line-strong bg-surface-2 text-fg-1' : 'border-line-subtle bg-surface-1 text-fg-3 hover:text-fg-1'"
        :aria-pressed="filter === entry.decision"
        @click="filter = entry.decision"
      >
        {{ entry.label }} <span class="font-mono text-[0.625rem]">{{ entry.count }}</span>
      </button>
    </div>

    <div v-if="rows.length === 0" class="rounded-lg border border-line-subtle bg-surface-1 p-2">
      <GovernEmptyState
        title="No linked runs"
        reason="No recorded decision in the sample joined to this rule with the selected decision."
        next-step="Choose another decision, or open the policy snapshot for rule-level context."
        action-label="Show all runs"
        @action="filter = 'all'"
      />
    </div>

    <div v-else class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
      <div class="ix-scroll overflow-x-auto">
        <table class="ix-agent-table" aria-label="Runs that fired this rule">
          <thead>
            <tr>
              <th scope="col" class="w-32">Time</th>
              <th scope="col" class="min-w-40">Run</th>
              <th scope="col" class="hidden w-40 min-[900px]:table-cell">Agent</th>
              <th scope="col" class="w-32">Decision</th>
              <th scope="col" class="hidden w-28 min-[1100px]:table-cell">Evidence</th>
              <th scope="col" class="hidden w-28 min-[1260px]:table-cell">Provenance</th>
              <th scope="col" class="w-10"><span class="sr-only">Open</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="run in rows" :key="run.runId">
              <td>
                <span class="text-xs text-fg-2" :title="formatGovernStamp(run.at)">{{ formatGovernRelative(run.at) }}</span>
              </td>
              <td>
                <NuxtLink :to="runHref(run.runId)" class="font-mono text-[0.6875rem] text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline">
                  {{ run.runId }}
                </NuxtLink>
                <span class="mt-0.5 block max-w-64 truncate text-[0.625rem] text-fg-3" :title="run.summary">{{ run.summary }}</span>
              </td>
              <td class="hidden min-[900px]:table-cell">
                <span class="block truncate text-xs text-fg-2">{{ run.agent }}</span>
                <span class="block font-mono text-[0.625rem] text-fg-3">{{ run.agentVersion }}</span>
              </td>
              <td><GovernDecisionPill :decision="run.decision" /></td>
              <td class="hidden min-[1100px]:table-cell">
                <span v-if="run.evidence" class="inline-flex items-center gap-1 text-xs text-fg-2">
                  <BadgeCheck v-if="run.evidence === 'certified'" :size="12" :stroke-width="1.9" class="text-ok" aria-hidden="true" />
                  <ScanLine v-else :size="12" :stroke-width="1.9" class="text-accent" aria-hidden="true" />
                  {{ run.evidence === "certified" ? "Certified" : "Sampled" }}
                </span>
                <GovernEmptyValue v-else reason="No evidence record joined to this decision" />
              </td>
              <td class="hidden min-[1260px]:table-cell">
                <span class="text-xs" :class="run.provenance === 'partial' ? 'text-warn' : 'text-fg-2'">{{ run.provenance === "partial" ? "Partial" : "Complete" }}</span>
              </td>
              <td>
                <NuxtLink
                  :to="runHref(run.runId)"
                  class="inline-flex size-6 items-center justify-center rounded text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                  :aria-label="`Open run ${run.runId}`"
                >
                  <ArrowUpRight :size="13" :stroke-width="1.9" aria-hidden="true" />
                </NuxtLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
