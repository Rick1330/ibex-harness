<script setup lang="ts">
import { computed, ref } from "vue"
import BudgetHeader from "./BudgetHeader.vue"
import BudgetLifecyclePanel from "./BudgetLifecyclePanel.vue"
import BudgetReservationsPanel from "./BudgetReservationsPanel.vue"
import GovernFilterBar from "@/components/console/govern/primitives/GovernFilterBar.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import GovernShortcutsDialog from "@/components/console/govern/primitives/GovernShortcutsDialog.vue"
import GovernTabBar from "@/components/console/govern/primitives/GovernTabBar.vue"
import { useGovernShortcuts } from "@/composables/useGovernShortcuts"
import { formatGovernRelative } from "@/lib/govern-format"
import {
  BUDGET_LIST_DEFAULT,
  BUDGET_TAB_LABELS,
  budgetHref,
  type BudgetListState,
  type BudgetTab,
} from "@/lib/govern-query"
import {
  BUDGET_LIFECYCLE,
  BUDGET_SCOPE_KINDS,
  BUDGET_SCOPE_LABELS,
  BUDGET_STATE_LABELS,
  ENFORCEMENTS,
  ENFORCEMENT_LABELS,
  budgetState,
  budgetUsd,
  filterLifecycle,
  filterReservations,
  reservationsFor,
  type BudgetWindow,
  type Enforcement,
  type BudgetScopeKind,
} from "@/lib/budget-preview"

const props = defineProps<{ state: BudgetListState }>()
const emit = defineEmits<{ update: [state: BudgetListState] }>()

function update(patch: Partial<BudgetListState>): void {
  emit("update", { ...props.state, ...patch })
}

const header = ref<InstanceType<typeof BudgetHeader> | null>(null)
const search = ref<InstanceType<typeof GovernFilterBar> | null>(null)


const allRows = computed(() => reservationsFor(props.state.window))
const allEvents = computed(() => BUDGET_LIFECYCLE)
const rows = computed(() => filterReservations(allRows.value, props.state))
const events = computed(() => filterLifecycle(allEvents.value, props.state))

const tabs = [
  { id: "reservations", label: BUDGET_TAB_LABELS.reservations },
  { id: "lifecycle", label: BUDGET_TAB_LABELS.lifecycle },
]

const tabBadges = computed(() => ({
  reservations: String(rows.value.length),
  lifecycle: String(events.value.length),
}))

const scopeOptions = [
  { value: "all", label: "All scopes" },
  ...BUDGET_SCOPE_KINDS.map((kind) => ({ value: kind, label: BUDGET_SCOPE_LABELS[kind] })),
]

const enforcementOptions = [
  { value: "all", label: "All enforcement" },
  ...ENFORCEMENTS.map((value) => ({ value, label: ENFORCEMENT_LABELS[value] })),
]

const atLimit = computed(() => allRows.value.filter((row) => budgetState(row) === "exhausted"))
const closeToLimit = computed(() => allRows.value.filter((row) => budgetState(row) === "tight"))
const newestHold = computed(() =>
  allRows.value
    .map((row) => row.lastReservationAt)
    .filter((value): value is string => value !== null)
    .sort((left, right) => Date.parse(right) - Date.parse(left))[0] ?? null,
)

const activeFilters = computed(
  () =>
    [
      props.state.q.trim() !== "",
      props.state.scope !== "all",
      props.state.enforcement !== "all",
    ].filter(Boolean).length,
)

function clearFilters(): void {
  emit("update", { ...BUDGET_LIST_DEFAULT, tab: props.state.tab, window: props.state.window })
}

function copyCurrentLink(): void {
  if (!import.meta.client) return
  void navigator.clipboard.writeText(`${window.location.origin}${budgetHref(props.state)}`)
}

const { helpOpen } = useGovernShortcuts({
  onSearch: () => search.value?.focus(),
  keys: {
    y: copyCurrentLink,
    "1": () => update({ tab: "reservations" }),
    "2": () => update({ tab: "lifecycle" }),
  },
})

const shortcutGroups = [
  {
    title: "This page",
    rows: [
      { keys: "/", label: "Focus the filter box" },
      { keys: "1 / 2", label: "Reservations · Lifecycle" },
      { keys: "y", label: "Copy link to this view" },
      { keys: "g p", label: "Go to policies" },
      { keys: "g a", label: "Go to audit log" },
      { keys: "?", label: "Show this sheet" },
    ],
  },
]
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">
    <BudgetHeader ref="header" :window="state.window" @update:window="update({ window: $event as BudgetWindow })" />

    <section v-if="atLimit.length > 0 || closeToLimit.length > 0" class="flex flex-wrap items-center gap-2" aria-label="Needs attention">
      <button
        v-if="atLimit.length > 0"
        type="button"
        class="inline-flex items-center gap-2 rounded-full border border-crit/40 bg-crit-tint px-2.5 py-1 text-xs text-crit transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        title="These scopes are at their hard ceiling; the runtime refuses further work."
        @click="update({ tab: 'reservations', scope: 'all', enforcement: 'hard' })"
      >
        <span class="font-mono text-sm leading-5 font-semibold tabular-nums">{{ atLimit.length }}</span>
        {{ BUDGET_STATE_LABELS.exhausted }}
      </button>
      <button
        v-if="closeToLimit.length > 0"
        type="button"
        class="inline-flex items-center gap-2 rounded-full border border-warn/40 bg-warn-tint px-2.5 py-1 text-xs text-warn transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        title="Ninety percent of the ceiling is used."
        @click="update({ tab: 'reservations', scope: 'all', enforcement: 'all' })"
      >
        <span class="font-mono text-sm leading-5 font-semibold tabular-nums">{{ closeToLimit.length }}</span>
        {{ BUDGET_STATE_LABELS.tight }}
      </button>
      <NuxtLink
        to="/audit?view=config"
        class="ml-auto inline-flex items-center gap-1 text-[0.6875rem] text-fg-3 underline decoration-line-strong underline-offset-2 hover:text-fg-1"
      >
        Limit changes in the audit log
      </NuxtLink>
    </section>

    <p v-else class="text-[0.6875rem] leading-4 text-fg-3">
      Every scope has headroom in this window.
      <span v-if="newestHold">Newest hold {{ formatGovernRelative(newestHold) }}.</span>
    </p>

    <GovernTabBar
      :tabs="tabs"
      :model-value="state.tab"
      aria-label="Budget views"
      :badges="tabBadges"
      @update:model-value="update({ tab: $event as BudgetTab })"
    />

    <GovernFilterBar
      ref="search"
      :model-value="state.q"
      :label="state.tab === 'reservations' ? 'Filter reservations' : 'Filter lifecycle events'"
      :placeholder="state.tab === 'reservations' ? 'Filter scopes: workspace, agent, key' : 'Filter events: hold, release, refusal'"
      :result-text="
        state.tab === 'reservations'
          ? `${rows.length} of ${allRows.length} scopes · ${budgetUsd(allRows.reduce((sum, row) => sum + row.committedUsd, 0))} committed`
          : `${events.length} of ${allEvents.length} lifecycle events`
      "
      :active="activeFilters > 0"
      @update:model-value="update({ q: $event })"
      @clear="clearFilters"
    >
      <template #filters>
        <GovernFilterSelect
          label="Scope"
          :model-value="state.scope"
          :options="scopeOptions"
          default-value="all"
          @update:model-value="update({ scope: $event as BudgetScopeKind | 'all' })"
        />
        <GovernFilterSelect
          v-if="state.tab === 'reservations'"
          label="Enforcement"
          :model-value="state.enforcement"
          :options="enforcementOptions"
          default-value="all"
          @update:model-value="update({ enforcement: $event as Enforcement | 'all' })"
        />
      </template>
    </GovernFilterBar>

    <BudgetReservationsPanel v-if="state.tab === 'reservations'" :rows="rows" :all-rows="allRows" />
    <BudgetLifecyclePanel v-else :rows="events" :all-rows="allEvents" />

    <GovernShortcutsDialog v-model:open="helpOpen" :groups="shortcutGroups" />
  </div>
</template>
