<script setup lang="ts">
import { computed, ref } from "vue"
import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, Minus, TriangleAlert } from "@lucide/vue"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import GovernConditionCode from "@/components/console/govern/primitives/GovernConditionCode.vue"
import GovernEffectTag from "@/components/console/govern/primitives/GovernEffectTag.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernEmptyValue from "@/components/console/govern/primitives/GovernEmptyValue.vue"
import GovernFilterBar from "@/components/console/govern/primitives/GovernFilterBar.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import GovernModeTag from "@/components/console/govern/primitives/GovernModeTag.vue"
import GovernPeekSheet from "@/components/console/govern/primitives/GovernPeekSheet.vue"
import GovernSparkline from "@/components/console/govern/primitives/GovernSparkline.vue"
import { formatGovernNumber, formatGovernRelative, formatGovernStamp, GOVERN_NOW } from "@/lib/govern-format"
import {
  POLICY_AREA_ORDER,
  POLICY_EFFECT_FILTER_LABELS,
  POLICY_MODE_FILTER_LABELS,
  filterPolicyRulesV2,
  policyChanged,
  policyFiredDelta,
  policyRuleApprovalStats,
  policyRuleLastFired,
  policyRuleProvenance,
  policyRuleSentence,
  policyRulesForSnapshot,
  policySnapshotWindow,
  sortPolicyRules,
  type PolicyRuleView,
} from "@/lib/policy-preview"
import {
  POLICY_EFFECT_FILTERS,
  POLICY_MODE_FILTERS,
  POLICY_RULE_SORT_LABELS,
  POLICY_RULE_SORTS,
  policyRuleDetailHref,
  policySnapshotHref,
  type PolicyListStateV2,
} from "@/lib/govern-query"
import { useTriageTable } from "@/composables/useTriageTable"

const props = defineProps<{
  state: PolicyListStateV2
  snapshotId: string
  returnTo: string
}>()

const emit = defineEmits<{ update: [state: PolicyListStateV2] }>()

function update(patch: Partial<PolicyListStateV2>): void {
  emit("update", { ...props.state, ...patch })
}

const all = computed(() => policyRulesForSnapshot(props.snapshotId))
const rows = computed(() =>
  sortPolicyRules(
    filterPolicyRulesV2(all.value, {
      q: props.state.q,
      effect: props.state.effect,
      mode: props.state.mode,
      area: props.state.area,
      changed: props.state.changed,
    }),
    props.state.sort,
  ),
)

const window = computed(() => policySnapshotWindow(props.snapshotId))
const changedCount = computed(() => all.value.filter(policyChanged).length)

const effectOptions = POLICY_EFFECT_FILTERS.map((value) => ({ value, label: POLICY_EFFECT_FILTER_LABELS[value] }))
const modeOptions = POLICY_MODE_FILTERS.map((value) => ({ value, label: POLICY_MODE_FILTER_LABELS[value] }))
const areaOptions = [
  { value: "all", label: "All areas" },
  ...POLICY_AREA_ORDER.map((area) => ({ value: area, label: area })),
]
const sortOptions = POLICY_RULE_SORTS.map((value) => ({ value, label: POLICY_RULE_SORT_LABELS[value] }))

const active = computed(
  () =>
    props.state.q.trim() !== "" ||
    props.state.effect !== "all" ||
    props.state.mode !== "all" ||
    props.state.area !== "all" ||
    props.state.changed ||
    props.state.sort !== "severity",
)

function clearFilters(): void {
  update({ q: "", effect: "all", mode: "all", area: "all", changed: false, sort: "severity" })
}

function ruleHref(rule: PolicyRuleView): string {
  const href = policyRuleDetailHref(rule.id, { tab: "overview", snapshot: props.snapshotId, rev: null })
  return `${href}?return=${encodeURIComponent(props.returnTo)}`
}

function provenance(rule: PolicyRuleView): { linked: number; partial: number; complete: number } {
  const base = policyRuleProvenance(rule.id)
  return base
}

const expanded = ref<Record<string, boolean>>({})
function toggleExpanded(id: string): void {
  expanded.value = { ...expanded.value, [id]: !expanded.value[id] }
}

const peekId = ref<string | null>(null)
const peekOpen = ref(false)
const peekRule = computed(() => rows.value.find((rule) => rule.id === peekId.value) ?? null)

const triage = useTriageTable<PolicyRuleView>({
  rows,
  onOpen: (rule) => void navigateTo(ruleHref(rule)),
  onPeek: (rule) => {
    peekId.value = rule.id
    peekOpen.value = true
  },
})

const searchBar = ref<InstanceType<typeof GovernFilterBar> | null>(null)
defineExpose({ focusSearch: () => searchBar.value?.focus() })

function deltaTone(direction: "up" | "down" | "flat" | "new"): string {
  if (direction === "up") return "text-warn"
  if (direction === "down") return "text-ok"
  if (direction === "new") return "text-accent"
  return "text-fg-3"
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <GovernFilterBar
      ref="searchBar"
      :model-value="state.q"
      placeholder="Search rules, areas, expressions"
      label="Search policy rules"
      :result-text="`${rows.length} of ${all.length} rules`"
      :active="active"
      @update:model-value="update({ q: $event })"
      @clear="clearFilters"
    >
      <template #filters>
        <GovernFilterSelect
          label="Effect"
          :model-value="state.effect"
          :options="effectOptions"
          default-value="all"
          @update:model-value="update({ effect: $event as PolicyListStateV2['effect'] })"
        />
        <GovernFilterSelect
          label="Mode"
          :model-value="state.mode"
          :options="modeOptions"
          default-value="all"
          @update:model-value="update({ mode: $event as PolicyListStateV2['mode'] })"
        />
        <GovernFilterSelect
          label="Area"
          :model-value="state.area"
          :options="areaOptions"
          default-value="all"
          @update:model-value="update({ area: $event as PolicyListStateV2['area'] })"
        />
        <button
          type="button"
          class="inline-flex h-8 items-center gap-1.5 rounded-full border px-2.5 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
          :class="state.changed ? 'border-accent/40 bg-accent-tint text-fg-1' : 'border-line-subtle bg-surface-1 text-fg-3 hover:border-line'"
          :aria-pressed="state.changed"
          @click="update({ changed: !state.changed })"
        >
          Changed in snapshot
          <span class="font-mono text-[0.625rem] tabular-nums" :class="state.changed ? 'text-fg-2' : 'text-fg-3'">{{ changedCount }}</span>
        </button>
      </template>
      <template #right>
        <GovernFilterSelect
          label="Sort"
          :model-value="state.sort"
          :options="sortOptions"
          default-value="severity"
          @update:model-value="update({ sort: $event as PolicyListStateV2['sort'] })"
        />
      </template>
    </GovernFilterBar>

    <div v-if="rows.length === 0" class="rounded-lg border border-line-subtle bg-surface-1 p-2">
      <GovernEmptyState
        title="No rules match these filters"
        :reason="state.changed ? 'No rule changed between the previous snapshot and this one.' : 'The search and filters exclude every rule in this snapshot.'"
        next-step="Clear the filters to see all rules in force."
        action-label="Clear filters"
        @action="clearFilters"
      />
    </div>

    <div v-else class="flex flex-col gap-2">
      <div class="flex flex-col gap-2 lg:hidden" aria-label="Policy rules on this viewport">
        <article
          v-for="rule in rows"
          :key="rule.id"
          :aria-label="`Open policy rule ${rule.label}`"
          class="rounded-lg border border-line-subtle bg-surface p-3"
        >
          <NuxtLink :to="ruleHref(rule)" class="block min-w-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
            <span class="flex items-start justify-between gap-2">
              <span class="min-w-0">
                <span class="block truncate text-xs font-medium text-fg-1">{{ rule.label }}</span>
                <span class="mt-0.5 block truncate font-mono text-[0.625rem] text-fg-3">{{ rule.id }}@{{ rule.revision.revision }} · {{ rule.owner }}</span>
              </span>
              <ChevronRight :size="14" :stroke-width="1.8" class="mt-0.5 shrink-0 text-fg-3" aria-hidden="true" />
            </span>
            <span class="mt-2 flex flex-wrap items-center gap-1.5">
              <GovernEffectTag :effect="rule.revision.effect" />
              <GovernModeTag :mode="rule.revision.mode" />
              <span v-if="policyChanged(rule)" class="ix-status-pill ix-status-pill-accent">Changed</span>
            </span>
            <span class="mt-2 block text-[0.6875rem] text-fg-3">
              {{ rule.fired }} fires in 7d · {{ rule.area }} · {{ rule.scope }}
            </span>
          </NuxtLink>
        </article>
      </div>
      <div class="hidden overflow-hidden rounded-lg border border-line-subtle bg-surface-1 lg:block">
      <div class="ix-scroll overflow-x-auto">
        <table class="ix-agent-table" aria-label="Policy rules in force">
          <thead>
            <tr>
              <th scope="col" class="w-8 !pl-2"><span class="sr-only">Expand</span></th>
              <th scope="col" class="min-w-56">Rule</th>
              <th scope="col" class="hidden w-24 min-[900px]:table-cell">Area</th>
              <th scope="col" class="w-32">Effect</th>
              <th scope="col" class="hidden w-28 min-[1180px]:table-cell">Mode</th>
              <th scope="col" class="w-44">Fired 7d</th>
              <th scope="col" class="hidden w-32 min-[1100px]:table-cell">Last fired</th>
              <th scope="col" class="hidden w-36 min-[1340px]:table-cell">Changed</th>
              <th scope="col" class="w-10"><span class="sr-only">Open</span></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="rule in rows" :key="rule.id">
              <tr v-bind="triage.rowAttrs(rule)" :aria-label="`Open ${rule.label}`">
                <td class="!pl-2">
                  <button
                    type="button"
                    class="inline-flex size-6 items-center justify-center rounded text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                    :aria-label="expanded[rule.id] ? `Collapse ${rule.label}` : `Expand ${rule.label} expression`"
                    @click.stop="toggleExpanded(rule.id)"
                  >
                    <component
                      :is="expanded[rule.id] ? ChevronDown : ChevronRight"
                      :size="13"
                      :stroke-width="1.9"
                      aria-hidden="true"
                    />
                  </button>
                </td>
                <td class="min-w-0">
                  <div class="flex min-w-0 items-center gap-1.5">
                    <NuxtLink
                      :to="ruleHref(rule)"
                      class="max-w-72 truncate text-[0.8125rem] font-medium text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                      @click.stop
                    >
                      {{ rule.label }}
                    </NuxtLink>
                    <span
                      v-if="policyChanged(rule)"
                      class="size-1.5 shrink-0 rounded-full bg-accent-memory"
                      role="img"
                      title="Changed in this snapshot"
                      aria-label="Changed in this snapshot"
                    />
                  </div>
                  <span class="mt-0.5 block truncate font-mono text-[0.625rem] leading-3 text-fg-3">
                    {{ rule.id }}@{{ rule.revision.revision }} · {{ rule.owner }}
                  </span>
                </td>
                <td class="hidden min-[900px]:table-cell">
                  <span class="text-xs text-fg-2">{{ rule.area }}</span>
                </td>
                <td>
                  <GovernEffectTag :effect="rule.revision.effect" :title="rule.revision.condition" />
                </td>
                <td class="hidden min-[1180px]:table-cell">
                  <GovernModeTag :mode="rule.revision.mode" />
                </td>
                <td>
                  <div v-if="rule.fired === null" class="flex items-center gap-1.5">
                    <GovernEmptyValue reason="No decision data joined for this rule" />
                    <span class="text-[0.6875rem] text-fg-3">Not reported</span>
                  </div>
                  <div v-else class="flex items-center gap-2">
                    <div class="min-w-0">
                      <div class="flex items-baseline gap-1.5">
                        <span class="font-mono text-[0.8125rem] font-semibold text-fg-1 tabular-nums">{{ formatGovernNumber(rule.fired) }}</span>
                        <span
                          class="inline-flex items-center gap-0.5 font-mono text-[0.625rem] tabular-nums"
                          :class="deltaTone(policyFiredDelta(rule).direction)"
                          :title="`Previous 7 days: ${formatGovernNumber(rule.firedPrev ?? 0)}`"
                        >
                          <ArrowUp v-if="policyFiredDelta(rule).direction === 'up'" :size="9" :stroke-width="2.4" aria-hidden="true" />
                          <ArrowDown v-else-if="policyFiredDelta(rule).direction === 'down'" :size="9" :stroke-width="2.4" aria-hidden="true" />
                          <Minus v-else :size="9" :stroke-width="2.4" aria-hidden="true" />
                          {{ policyFiredDelta(rule).label }}
                        </span>
                      </div>
                      <span class="mt-0.5 block text-[0.625rem] text-fg-3">14-day trend</span>
                    </div>
                    <GovernSparkline :points="rule.firedTrend" :label="`${rule.label} fired per day, last 14 days`" illustrative />
                    <Tooltip v-if="provenance(rule).partial > 0" :delay-duration="120">
                      <TooltipTrigger as-child>
                        <span tabindex="0" class="inline-flex text-warn" role="img" aria-label="Partial provenance">
                          <TriangleAlert :size="12" :stroke-width="1.9" aria-hidden="true" />
                        </span>
                      </TooltipTrigger>
                      <TooltipContent side="top" class="!max-w-72 !text-xs">
                        {{ provenance(rule).partial }} of {{ provenance(rule).linked }} linked runs have partial provenance, so this count may be low.
                      </TooltipContent>
                    </Tooltip>
                  </div>
                </td>
                <td class="hidden min-[1100px]:table-cell">
                  <span v-if="policyRuleLastFired(rule.id)" class="text-xs text-fg-2" :title="formatGovernStamp(policyRuleLastFired(rule.id)!.at)">
                    {{ formatGovernRelative(policyRuleLastFired(rule.id)!.at, GOVERN_NOW) }}
                  </span>
                  <GovernEmptyValue v-else reason="This rule has not fired in the sampled decisions" />
                </td>
                <td class="hidden min-[1340px]:table-cell">
                  <span class="block text-xs text-fg-2" :title="formatGovernStamp(rule.revision.effectiveFrom)">
                    {{ formatGovernRelative(rule.revision.effectiveFrom, GOVERN_NOW) }}
                  </span>
                  <span class="mt-0.5 block truncate text-[0.625rem] text-fg-3">{{ rule.revision.changedBy }}</span>
                </td>
                <td>
                  <NuxtLink
                    :to="ruleHref(rule)"
                    class="inline-flex size-6 items-center justify-center rounded text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                    :aria-label="`Open ${rule.label}`"
                    @click.stop
                  >
                    <ChevronRight :size="14" :stroke-width="1.9" aria-hidden="true" />
                  </NuxtLink>
                </td>
              </tr>
              <tr v-if="expanded[rule.id]" class="bg-canvas/40">
                <td colspan="9" class="!py-0 !pl-12">
                  <div class="grid gap-x-8 gap-y-2 py-3 pr-4 pl-3 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
                    <div class="min-w-0">
                      <p class="text-[0.6875rem] font-medium tracking-[0.06em] text-fg-3 uppercase">Plain language</p>
                      <p class="mt-1 text-xs leading-5 text-fg-2">
                        {{ policyRuleSentence(rule.revision) ?? rule.revision.summary }}
                      </p>
                    </div>
                    <div class="min-w-0">
                      <p class="text-[0.6875rem] font-medium tracking-[0.06em] text-fg-3 uppercase">Expression</p>
                      <div class="mt-1"><GovernConditionCode :code="rule.revision.condition" /></div>
                      <p class="mt-1.5 font-mono text-[0.625rem] leading-4 text-fg-3">
                        Evaluated in {{ window.from ? formatGovernStamp(window.from) : "this snapshot" }} · scope {{ rule.scope }}
                      </p>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
        <footer class="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line-subtle bg-canvas/30 px-4 py-1.5 text-[0.6875rem] leading-4 text-fg-3">
          <span>Effect labels describe what a recorded rule does. Runtime precedence between rules is not reported yet.</span>
          <span class="ml-auto font-mono">{{ snapshotId }}</span>
        </footer>
      </div>
    </div>

    <GovernPeekSheet
      v-if="peekRule"
      v-model:open="peekOpen"
      :title="peekRule.label"
      :description="`${peekRule.id}@${peekRule.revision.revision} · ${peekRule.area} · ${peekRule.scope}`"
      :href="ruleHref(peekRule)"
      href-label="Open rule"
    >
      <div class="space-y-3">
        <div class="flex flex-wrap items-center gap-1.5">
          <GovernEffectTag :effect="peekRule.revision.effect" />
          <GovernModeTag :mode="peekRule.revision.mode" />
          <span v-if="policyChanged(peekRule)" class="ix-preview-chip">Changed in {{ snapshotId }}</span>
        </div>
        <p class="text-sm leading-5 text-fg-2">
          {{ policyRuleSentence(peekRule.revision) ?? peekRule.revision.summary }}
        </p>
        <GovernConditionCode :code="peekRule.revision.condition" />
        <dl class="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line-subtle bg-line-subtle">
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Fired (7 days)</dt>
            <dd class="mt-0.5 font-mono text-sm text-fg-1 tabular-nums">
              {{ peekRule.fired === null ? "Not reported" : formatGovernNumber(peekRule.fired) }}
            </dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Delta</dt>
            <dd class="mt-0.5 font-mono text-sm tabular-nums" :class="deltaTone(policyFiredDelta(peekRule).direction)">
              {{ policyFiredDelta(peekRule).label }}
            </dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Linked runs</dt>
            <dd class="mt-0.5 font-mono text-sm text-fg-1 tabular-nums">{{ provenance(peekRule).linked }}</dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Partial provenance</dt>
            <dd class="mt-0.5 font-mono text-sm tabular-nums" :class="provenance(peekRule).partial > 0 ? 'text-warn' : 'text-fg-1'">
              {{ provenance(peekRule).partial }}
            </dd>
          </div>
        </dl>
        <div v-if="peekRule.revision.effect === 'require_approval'" class="rounded-lg border border-line-subtle bg-surface-2 px-3 py-2 text-xs leading-5 text-fg-2">
          <p class="font-medium text-fg-1">Approvals in this snapshot</p>
          <p class="mt-0.5">
            {{ policyRuleApprovalStats(peekRule.id).granted }} granted ·
            {{ policyRuleApprovalStats(peekRule.id).denied }} denied ·
            {{ policyRuleApprovalStats(peekRule.id).pending }} pending
            <template v-if="policyRuleApprovalStats(peekRule.id).medianMinutes !== null">
              · median {{ policyRuleApprovalStats(peekRule.id).medianMinutes }} min
            </template>
          </p>
        </div>
        <div class="flex flex-wrap gap-3 border-t border-line-subtle pt-2 text-xs">
          <NuxtLink :to="ruleHref(peekRule)" class="text-fg-2 underline decoration-line-strong underline-offset-3 hover:text-fg-1">Rule detail</NuxtLink>
          <NuxtLink :to="policySnapshotHref(snapshotId)" class="text-fg-2 underline decoration-line-strong underline-offset-3 hover:text-fg-1">Snapshot</NuxtLink>
        </div>
      </div>
    </GovernPeekSheet>
  </div>
</template>
