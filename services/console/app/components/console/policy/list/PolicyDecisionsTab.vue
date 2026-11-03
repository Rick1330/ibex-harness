<script setup lang="ts">
import { computed, ref } from "vue"
import { ArrowUpRight, BadgeCheck, ScanLine } from "@lucide/vue"
import GovernDecisionPill from "@/components/console/govern/primitives/GovernDecisionPill.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernEmptyValue from "@/components/console/govern/primitives/GovernEmptyValue.vue"
import GovernFilterBar from "@/components/console/govern/primitives/GovernFilterBar.vue"
import GovernPeekSheet from "@/components/console/govern/primitives/GovernPeekSheet.vue"
import { formatGovernNumber, formatGovernRelative, formatGovernStamp, GOVERN_NOW } from "@/lib/govern-format"
import {
  POLICY_DECISION_LABELS,
  POLICY_DECISION_ORDER,
  policyDecisionCounts,
  policyDecisionsSince,
  policyRuleById,
  type PolicyDecisionKind,
  type PolicyRunDecision,
} from "@/lib/policy-preview"
import {
  POLICY_DECISION_RANGE_LABELS,
  POLICY_DECISION_RANGES,
  policyResolveHref,
  policyRuleDetailHref,
  type PolicyDecisionRange,
  type PolicyListStateV2,
} from "@/lib/govern-query"
import { useTriageTable } from "@/composables/useTriageTable"

const props = defineProps<{
  state: PolicyListStateV2
  snapshotId: string
}>()

const emit = defineEmits<{ update: [state: PolicyListStateV2] }>()

function update(patch: Partial<PolicyListStateV2>): void {
  emit("update", { ...props.state, ...patch })
}

const windowMs: Record<PolicyDecisionRange, number> = { "7d": 7 * 86_400_000, "30d": 30 * 86_400_000 }
const since = computed(() => new Date(GOVERN_NOW - windowMs[props.state.range]).toISOString())

const counts = computed(() => policyDecisionCounts(props.snapshotId, since.value))
const total = computed(() => counts.value.reduce((sum, entry) => sum + entry.count, 0))

type DecisionRow = { id: string; decision: PolicyRunDecision }

const decisions = computed<DecisionRow[]>(() => {
  const query = props.state.q.trim().toLowerCase()
  return policyDecisionsSince(since.value, props.snapshotId)
    .filter((decision) => props.state.decision === "all" || decision.decision === props.state.decision)
    .filter((decision) => {
      if (!query) return true
      const label = policyRuleById(decision.ruleId)?.label ?? decision.ruleId
      return [decision.runId, decision.agent, decision.agentVersion, decision.ruleId, label, decision.summary].some((value) =>
        value.toLowerCase().includes(query),
      )
    })
    .map((decision) => ({ id: `${decision.runId}:${decision.ruleId}`, decision }))
})

const visibleDecisions = computed(() => decisions.value.map((row) => row.decision))

const segmentTone: Record<PolicyDecisionKind, string> = {
  blocked: "bg-crit",
  approval: "bg-warn",
  redacted: "bg-memory",
  wrapped: "bg-accent-memory",
  tombstoned: "bg-line-strong",
  allowed: "bg-ok",
}

const decisionOptions = [
  { value: "all", label: "All decisions" },
  ...POLICY_DECISION_ORDER.map((value) => ({ value, label: POLICY_DECISION_LABELS[value] })),
]

function ruleHref(decision: PolicyRunDecision): string {
  return policyRuleDetailHref(decision.ruleId, { tab: "fires", snapshot: decision.snapshotId, rev: null })
}

function runHref(decision: PolicyRunDecision): string {
  return policyResolveHref({ run: decision.runId, at: "" })
}

const peekId = ref<string | null>(null)
const peekOpen = ref(false)
const peekDecision = computed(
  () => visibleDecisions.value.find((decision) => `${decision.runId}:${decision.ruleId}` === peekId.value) ?? null,
)

const triage = useTriageTable<DecisionRow>({
  rows: decisions,
  onOpen: (row) => void navigateTo(runHref(row.decision)),
  onPeek: (row) => {
    peekId.value = row.id
    peekOpen.value = true
  },
})

const searchBar = ref<InstanceType<typeof GovernFilterBar> | null>(null)
defineExpose({ focusSearch: () => searchBar.value?.focus() })

function clearFilters(): void {
  update({ q: "", decision: "all" })
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <GovernFilterBar
      ref="searchBar"
      :model-value="state.q"
      placeholder="Search runs, agents, rules"
      label="Search decisions"
      :result-text="`${decisions.length} of ${total} linked decisions`"
      :active="state.q.trim() !== '' || state.decision !== 'all'"
      @update:model-value="update({ q: $event })"
      @clear="clearFilters"
    >
      <template #filters>
        <div class="flex items-center rounded-lg border border-line-subtle bg-surface-1 p-0.5" role="group" aria-label="Decision range">
          <button
            v-for="range in POLICY_DECISION_RANGES"
            :key="range"
            type="button"
            class="inline-flex h-7 items-center rounded-md px-2.5 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            :class="state.range === range ? 'bg-surface-2 text-fg-1 outline outline-1 outline-line-strong' : 'text-fg-3 hover:text-fg-1'"
            :aria-pressed="state.range === range"
            @click="update({ range })"
          >
            {{ POLICY_DECISION_RANGE_LABELS[range] }}
          </button>
        </div>
        <label class="relative inline-flex h-8 items-center gap-1 rounded-full border px-2.5 text-xs transition-colors" :class="state.decision !== 'all' ? 'border-accent/40 bg-accent-tint text-fg-1' : 'border-line-subtle bg-surface-1 text-fg-3 hover:border-line'">
          <span class="shrink-0 text-fg-3">Decision:</span>
          <select
            :value="state.decision"
            aria-label="Filter by decision"
            class="cursor-pointer appearance-none bg-transparent pr-4 font-medium text-current outline-none"
            @change="update({ decision: ($event.target as HTMLSelectElement).value as PolicyListStateV2['decision'] })"
          >
            <option v-for="option in decisionOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </label>
      </template>
      <template #right>
        <span>{{ POLICY_DECISION_RANGE_LABELS[state.range] }}</span>
      </template>
    </GovernFilterBar>

    <section class="rounded-lg border border-line-subtle bg-surface-1" aria-label="Decision mix">
      <header class="flex flex-wrap items-baseline justify-between gap-2 px-4 pt-3">
        <div>
          <h2 class="text-sm font-semibold text-fg-1">What the runtime decided</h2>
          <p class="mt-0.5 text-xs text-fg-3">
            {{ formatGovernNumber(total) }} linked decisions in {{ POLICY_DECISION_RANGE_LABELS[state.range].toLowerCase() }} ·
            snapshot {{ snapshotId }}
          </p>
        </div>
        <span class="flex items-center gap-2 font-mono text-[0.6875rem] text-fg-3">
          linked run sample
          <span class="inline-flex h-5 items-center rounded-full border border-warn/30 bg-warn-tint px-2 font-sans text-[0.625rem] font-medium text-warn">Illustrative</span>
        </span>
      </header>

      <div v-if="total === 0" class="px-4 py-6 text-xs text-fg-3">
        No linked decisions in this window for this snapshot.
      </div>
      <div v-else class="px-4 pt-3 pb-3">
        <div class="relative">
          <div class="flex h-7 w-full overflow-hidden rounded-md" role="img" :aria-label="`Decision mix: ${counts.map((entry) => `${entry.label} ${entry.count}`).join(', ')}`">
            <span
              v-for="entry in counts.filter((item) => item.count > 0)"
              :key="entry.decision"
              class="h-full"
              :class="segmentTone[entry.decision]"
              :style="{ width: `${(entry.count / total) * 100}%` }"
              :title="`${entry.label}: ${entry.count}`"
            />
          </div>
          <div class="ix-hatch pointer-events-none absolute inset-0 rounded-md opacity-50" aria-hidden="true" />
        </div>
        <ul class="mt-2 flex flex-wrap gap-x-4 gap-y-1.5">
          <li v-for="entry in counts" :key="entry.decision" class="flex items-center gap-1.5 text-xs text-fg-2">
            <span class="size-2 rounded-sm" :class="segmentTone[entry.decision]" aria-hidden="true" />
            {{ entry.label }}
            <span class="font-mono text-[0.6875rem] text-fg-3 tabular-nums">{{ entry.count }}</span>
          </li>
        </ul>
        <p class="mt-2 border-t border-line-subtle pt-2 text-[0.6875rem] leading-4 text-fg-3">
          Only decisions joined to a run appear here. The full decision log is not connected, so these counts are a sample, never a total.
        </p>
      </div>
    </section>

    <div v-if="decisions.length === 0" class="rounded-lg border border-line-subtle bg-surface-1 p-2">
      <GovernEmptyState
        title="No decisions match these filters"
        reason="No linked run in this window carries the selected decision."
        next-step="Choose a different decision or widen the range."
        action-label="Clear filters"
        @action="clearFilters"
      />
    </div>

    <div v-else class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
      <div class="ix-scroll overflow-x-auto">
        <table class="ix-agent-table" aria-label="Linked run decisions">
          <thead>
            <tr>
              <th scope="col" class="w-24">Time</th>
              <th scope="col" class="min-w-36">Run</th>
              <th scope="col" class="hidden w-40 min-[1024px]:table-cell">Agent</th>
              <th scope="col" class="min-w-40">Rule</th>
              <th scope="col" class="w-36">Decision</th>
              <th scope="col" class="hidden w-28 min-[1200px]:table-cell">Evidence</th>
              <th scope="col" class="hidden w-24 min-[1360px]:table-cell">Provenance</th>
              <th scope="col" class="w-10"><span class="sr-only">Open</span></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in decisions"
              :key="row.id"
              v-bind="triage.rowAttrs(row)"
              :aria-label="`Open run ${row.decision.runId}`"
            >
              <td>
                <span class="text-xs whitespace-nowrap text-fg-2" :title="formatGovernStamp(row.decision.at)">{{ formatGovernRelative(row.decision.at, GOVERN_NOW) }}</span>
              </td>
              <td>
                <span class="block truncate font-mono text-[0.6875rem] text-fg-2">{{ row.decision.runId }}</span>
                <span class="mt-0.5 block truncate text-[0.625rem] text-fg-3">{{ row.decision.summary }}</span>
              </td>
              <td class="hidden min-[1024px]:table-cell">
                <span class="block truncate text-xs text-fg-2">{{ row.decision.agent }}</span>
                <span class="block font-mono text-[0.625rem] text-fg-3">{{ row.decision.agentVersion }}</span>
              </td>
              <td>
                <NuxtLink
                  :to="ruleHref(row.decision)"
                  class="block max-w-64 truncate text-xs text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline"
                  @click.stop
                >
                  {{ policyRuleById(row.decision.ruleId)?.label ?? row.decision.ruleId }}
                </NuxtLink>
                <span class="mt-0.5 block truncate font-mono text-[0.625rem] text-fg-3">
                  {{ row.decision.ruleId }}@{{ row.decision.ruleRevision }}
                </span>
              </td>
              <td><GovernDecisionPill :decision="row.decision.decision" /></td>
              <td class="hidden min-[1200px]:table-cell">
                <span v-if="row.decision.evidence" class="inline-flex items-center gap-1 text-xs whitespace-nowrap text-fg-2">
                  <BadgeCheck v-if="row.decision.evidence === 'certified'" :size="12" :stroke-width="1.9" class="text-ok" aria-hidden="true" />
                  <ScanLine v-else :size="12" :stroke-width="1.9" class="text-accent" aria-hidden="true" />
                  {{ row.decision.evidence === "certified" ? "Certified" : "Sampled" }}
                </span>
                <GovernEmptyValue v-else reason="No evidence record joined to this decision" />
              </td>
              <td class="hidden min-[1360px]:table-cell">
                <span class="text-xs" :class="row.decision.provenance === 'partial' ? 'text-warn' : 'text-fg-2'">
                  {{ row.decision.provenance === "partial" ? "Partial" : "Complete" }}
                </span>
              </td>
              <td>
                <NuxtLink
                  :to="runHref(row.decision)"
                  class="inline-flex size-6 items-center justify-center rounded text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                  :aria-label="`Open run ${row.decision.runId}`"
                  @click.stop
                >
                  <ArrowUpRight :size="13" :stroke-width="1.9" aria-hidden="true" />
                </NuxtLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <GovernPeekSheet
      v-if="peekDecision"
      v-model:open="peekOpen"
      :title="`${policyRuleById(peekDecision.ruleId)?.label ?? peekDecision.ruleId}@${peekDecision.ruleRevision}`"
      :description="`${peekDecision.runId} · ${peekDecision.agent} ${peekDecision.agentVersion}`"
      :href="runHref(peekDecision)"
      href-label="Open run resolver"
    >
      <div class="space-y-3">
        <div class="flex flex-wrap items-center gap-1.5">
          <GovernDecisionPill :decision="peekDecision.decision" />
          <span class="font-mono text-[0.6875rem] text-fg-3" :title="formatGovernStamp(peekDecision.at)">{{ formatGovernRelative(peekDecision.at, GOVERN_NOW) }}</span>
        </div>
        <p class="text-sm leading-5 text-fg-2">{{ peekDecision.summary }}</p>
        <dl class="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line-subtle bg-line-subtle">
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Snapshot</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1">{{ peekDecision.snapshotId }}</dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Effect</dt>
            <dd class="mt-0.5 text-xs text-fg-1">{{ peekDecision.effect }}</dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Evidence</dt>
            <dd class="mt-0.5 text-xs text-fg-1">{{ peekDecision.evidence ?? "Not recorded" }}</dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Provenance</dt>
            <dd class="mt-0.5 text-xs" :class="peekDecision.provenance === 'partial' ? 'text-warn' : 'text-fg-1'">
              {{ peekDecision.provenance === "partial" ? "Partial" : "Complete" }}
            </dd>
          </div>
        </dl>
        <div v-if="peekDecision.approval" class="rounded-lg border border-line-subtle bg-surface-2 px-3 py-2 text-xs leading-5 text-fg-2">
          <p class="font-medium text-fg-1">Person's response</p>
          <p class="mt-0.5">
            {{ peekDecision.approval.state === "granted" ? "Granted" : peekDecision.approval.state === "denied" ? "Denied" : "Waiting on a person" }}
            by {{ peekDecision.approval.by ?? "Not recorded" }}
            <template v-if="peekDecision.approval.minutes !== null"> · {{ peekDecision.approval.minutes }} min</template>
          </p>
        </div>
      </div>
    </GovernPeekSheet>
  </div>
</template>
