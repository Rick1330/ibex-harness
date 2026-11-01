<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import {
  ArrowDown,
  ArrowUp,
  ArrowUpRight,
  CircleSlash,
  Copy,
  Ellipsis,
  ExternalLink,
  Link2,
  Lock,
  Pause,
  Rows3,
  Search,
  TriangleAlert,
  X,
} from "@lucide/vue"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import AgentListHeader from "./AgentListHeader.vue"
import AgentQuickLook from "./AgentQuickLook.vue"
import AgentMultiFilter from "./primitives/AgentMultiFilter.vue"
import AgentAttentionItem from "../primitives/AgentAttentionItem.vue"
import AgentBudgetBar from "../primitives/AgentBudgetBar.vue"
import AgentEnvTag from "../primitives/AgentEnvTag.vue"
import AgentHealthDot from "../primitives/AgentHealthDot.vue"
import AgentMetricCell from "../primitives/AgentMetricCell.vue"
import AgentStatusPill from "../primitives/AgentStatusPill.vue"
import MemoryKbd from "@/components/console/memory/list/primitives/MemoryKbd.vue"
import BrandIcon from "@/components/console/BrandIcon.vue"
import {
  agentAttentionHref,
  formatAgentCount,
  formatAgentMoney,
  formatAgentPercent,
  formatAgentRelative,
  formatAgentStamp,
} from "@/lib/agent-detail"
import {
  activeAgentFilterChips,
  agentIsNearBudget,
  agentNeedsAttention,
  agentOptions,
  agentRowEdge,
  agentViewCounts,
  filterAgents,
  groupAgents,
  sortAgents,
} from "@/lib/agent-list"
import {
  AGENT_DEFAULT_SORT_DIRECTION,
  AGENT_ENVS,
  AGENT_GROUP_KEYS,
  AGENT_GROUP_LABELS,
  AGENT_HEALTH_STATES,
  AGENT_SORT_KEYS,
  AGENT_SORT_LABELS,
  AGENT_STATUSES,
  AGENT_VIEW_LABELS,
  AGENT_VIEWS,
  type AgentGroupKey,
  type AgentListState,
  type AgentSortKey,
  type AgentView,
} from "@/lib/agent-list-query"
import {
  AGENT_ERROR_BAND_PCT,
  agentBudgetLeftUsd,
  agentHealthLabel,
  agentProviderLabel,
  agentStatusLabel,
  agentSummaries,
  agentTotals,
  sortAttention,
  type AgentSummary,
} from "@/lib/agent-preview"

const props = defineProps<{
  state: AgentListState
  returnTo: string
}>()

const emit = defineEmits<{ update: [state: AgentListState] }>()

const EMPTY_FILTERS: Partial<AgentListState> = {
  search: "",
  view: "all",
  statuses: [],
  envs: [],
  models: [],
  owners: [],
  healths: [],
  includeNoData: false,
}

function update(patch: Partial<AgentListState>): void {
  emit("update", { ...props.state, ...patch })
}

// ---- derived rows --------------------------------------------------------
const filtered = computed(() =>
  sortAgents(filterAgents(agentSummaries, props.state), props.state.sort, props.state.direction),
)
const grouped = computed(() => groupAgents(filtered.value, props.state.group))
const viewCounts = computed(() => agentViewCounts(agentSummaries))
const options = computed(() => agentOptions(agentSummaries))
const chips = computed(() => activeAgentFilterChips(props.state))
const totalAll = agentSummaries.length

const attentionAgents = computed(() =>
  sortAgents(agentSummaries.filter(agentNeedsAttention), "health", "asc"),
)
const attentionCount = computed(() => attentionAgents.value.length)
const failingCount = computed(() => agentSummaries.filter((agent) => agent.health === "failing").length)
const warningCount = computed(() => agentSummaries.filter((agent) => agent.health === "attention").length)
const errorAgentsAbove = computed(
  () => agentSummaries.filter((agent) => (agent.stats.errorRate ?? 0) > AGENT_ERROR_BAND_PCT).length,
)
const noDataHidden = computed(() => (props.state.includeNoData ? 0 : agentTotals.agentsWithoutData))

const statusOptions = computed(() =>
  AGENT_STATUSES.map((status) => ({
    value: status,
    label: agentStatusLabel(status),
    count: agentSummaries.filter((agent) => agent.status === status).length,
  })),
)
const envOptions = computed(() =>
  AGENT_ENVS.map((env) => ({
    value: env,
    label: env,
    count: agentSummaries.filter((agent) => agent.env === env).length,
  })),
)
const healthOptions = computed(() =>
  AGENT_HEALTH_STATES.map((health) => ({
    value: health,
    label: agentHealthLabel(health),
    count: agentSummaries.filter((agent) => agent.health === health).length,
  })),
)

// ---- search input (150 ms debounce, URL writes stay out of the way) ------
const searchInput = ref<HTMLInputElement | null>(null)
const searchDraft = ref(props.state.search)
let searchTimer: ReturnType<typeof setTimeout> | null = null

watch(
  () => props.state.search,
  (value) => {
    if (value !== searchDraft.value) searchDraft.value = value
  },
)

function onSearchInput(value: string): void {
  searchDraft.value = value
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    if (value !== props.state.search) update({ search: value })
  }, 150)
}

function submitSearch(): void {
  if (searchTimer) clearTimeout(searchTimer)
  if (searchDraft.value !== props.state.search) update({ search: searchDraft.value })
}

// ---- navigation ----------------------------------------------------------
function agentHref(agent: AgentSummary): string {
  return `/agents/${encodeURIComponent(agent.id)}?return=${encodeURIComponent(props.returnTo)}`
}

function openAgent(agent: AgentSummary, event?: MouseEvent): void {
  const href = agentHref(agent)
  if (event && (event.metaKey || event.ctrlKey || event.shiftKey)) {
    window.open(href, "_blank", "noopener")
    return
  }
  void navigateTo(href)
}

function copyText(value: string): void {
  if (import.meta.client) void navigator.clipboard.writeText(value)
}

function currentOrigin(): string {
  return import.meta.client ? window.location.origin : ""
}

function toggleSort(key: AgentSortKey): void {
  if (props.state.sort === key) {
    update({ direction: props.state.direction === "asc" ? "desc" : "asc" })
  } else {
    update({ sort: key, direction: AGENT_DEFAULT_SORT_DIRECTION[key] })
  }
}

function ariaSort(key: AgentSortKey): "ascending" | "descending" | "none" {
  if (props.state.sort !== key) return "none"
  return props.state.direction === "asc" ? "ascending" : "descending"
}

function sortIcon(key: AgentSortKey) {
  if (props.state.sort !== key) return ArrowUp
  return props.state.direction === "asc" ? ArrowUp : ArrowDown
}

function setView(view: AgentView): void {
  update({ view })
}

// ---- keyboard selection and quick look -----------------------------------
const selectedIndex = ref(-1)
const selectedId = computed(() => filtered.value[selectedIndex.value]?.id ?? null)
const quickLookOpen = ref(false)
const quickLookId = ref<string | null>(null)
const quickLookAgent = computed(() => filtered.value.find((agent) => agent.id === quickLookId.value) ?? null)
let hoverTimer: ReturnType<typeof setTimeout> | null = null
let hoverCooldownUntil = 0

function openQuickLook(agent: AgentSummary): void {
  quickLookId.value = agent.id
  quickLookOpen.value = true
}

function closeQuickLook(open: boolean): void {
  quickLookOpen.value = open
  if (!open) hoverCooldownUntil = Date.now() + 800
}

function moveSelection(delta: number): void {
  if (!filtered.value.length) return
  const current = filtered.value.findIndex((agent) => agent.id === quickLookId.value)
  const start = current >= 0 ? current : selectedIndex.value
  const next = (start + delta + filtered.value.length) % filtered.value.length
  selectedIndex.value = next
  if (quickLookOpen.value) quickLookId.value = filtered.value[next]!.id
  void nextTick(() => {
    document.querySelector<HTMLElement>(`[data-agent-row="${filtered.value[next]!.id}"]`)?.focus()
  })
}

function onRowKeydown(event: KeyboardEvent, agent: AgentSummary): void {
  if (event.key === "Enter") {
    event.preventDefault()
    openAgent(agent)
  } else if (event.key === " ") {
    event.preventDefault()
    openQuickLook(agent)
  }
}

function onRowEnter(agent: AgentSummary, event?: MouseEvent): void {
  if (Date.now() < hoverCooldownUntil) return
  // Do not slide the quick-look sheet under the pointer.
  if (event && import.meta.client && event.clientX > window.innerWidth - 460) return
  if (hoverTimer) clearTimeout(hoverTimer)
  hoverTimer = setTimeout(() => openQuickLook(agent), 400)
}

function onRowLeave(): void {
  if (hoverTimer) {
    clearTimeout(hoverTimer)
    hoverTimer = null
  }
}

// ---- attention sheet, filters focus, shortcuts ---------------------------
const attentionSheetOpen = ref(false)
const shortcutsDialog = ref<HTMLDialogElement | null>(null)
const statusFilterRef = ref<HTMLElement | null>(null)

const attentionGroups = computed(() =>
  attentionAgents.value.map((agent) => ({ agent, items: sortAttention(agent.attention) })),
)

function focusFilters(): void {
  statusFilterRef.value?.querySelector<HTMLButtonElement>("button")?.focus()
}

function isTypingTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && Boolean(target.closest("input, textarea, select, [contenteditable]"))
}

function onGlobalKeydown(event: KeyboardEvent): void {
  if (event.metaKey || event.ctrlKey || event.altKey) return
  if (isTypingTarget(event.target)) return
  if (event.key === "/") {
    event.preventDefault()
    searchInput.value?.focus()
    searchInput.value?.select()
  } else if (event.key === "j" || event.key === "J") {
    event.preventDefault()
    moveSelection(1)
  } else if (event.key === "k" || event.key === "K") {
    event.preventDefault()
    moveSelection(-1)
  } else if (event.key === "f" || event.key === "F") {
    event.preventDefault()
    focusFilters()
  } else if (event.key === "?") {
    event.preventDefault()
    shortcutsDialog.value?.showModal()
  } else if (event.key === "Escape") {
    if (quickLookOpen.value) closeQuickLook(false)
    else if (shortcutsDialog.value?.open) shortcutsDialog.value.close()
    else if (searchDraft.value) {
      searchDraft.value = ""
      update({ search: "" })
    }
  } else if (event.key === "Enter" && selectedIndex.value >= 0) {
    const agent = filtered.value[selectedIndex.value]
    if (agent && (event.target === document.body || event.target === document.documentElement)) {
      event.preventDefault()
      openAgent(agent)
    }
  }
}

onMounted(() => window.addEventListener("keydown", onGlobalKeydown))
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onGlobalKeydown)
  if (hoverTimer) clearTimeout(hoverTimer)
  if (searchTimer) clearTimeout(searchTimer)
})
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-2 pb-2">
    <AgentListHeader :state="state" :records="filtered" @status="(status) => update({ statuses: [status] })" />

    <!-- Health summary: four tiles that answer "is this OK?" -->
    <section class="grid grid-cols-2 divide-y divide-line-subtle overflow-hidden rounded-lg border border-line-subtle bg-surface sm:grid-cols-4 sm:divide-x sm:divide-y-0" aria-label="Agent summary">
      <button
        type="button"
        class="flex min-w-0 flex-col justify-center gap-0.5 px-3 py-2.5 text-left transition-colors hover:bg-raised focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-accent"
        @click="setView('attention')"
      >
        <span class="flex items-center gap-1 text-xs leading-4 text-fg-3">
          Needs attention
          <Tooltip :delay-duration="150">
            <TooltipTrigger as-child>
              <span tabindex="0" class="cursor-help text-fg-3" aria-label="How this is computed">ⓘ</span>
            </TooltipTrigger>
            <TooltipContent side="top" class="!max-w-64 !text-xs">
              Failing or attention-level agents: suspended, deploy failed, error rate above band, retries above band,
              budget under floor, drift advisory, low trace coverage, latency over budget, or quarantined memories.
            </TooltipContent>
          </Tooltip>
        </span>
        <span class="ix-kpi" :class="attentionCount ? 'text-warn' : 'text-fg-1'">
          {{ attentionCount }}<span class="text-sm font-medium text-fg-3"> of {{ totalAll }}</span>
        </span>
        <span class="truncate text-xs leading-4 text-fg-3">
          {{ warningCount }} warnings · {{ failingCount }} failing
        </span>
      </button>

      <div class="flex min-w-0 flex-col justify-center gap-0.5 px-3 py-2.5">
        <span class="flex items-center gap-1 text-xs leading-4 text-fg-3">
          Error rate
          <Tooltip :delay-duration="150">
            <TooltipTrigger as-child>
              <span tabindex="0" class="cursor-help text-fg-3" aria-label="How this is computed">ⓘ</span>
            </TooltipTrigger>
            <TooltipContent side="top" class="!max-w-64 !text-xs">
              Run-weighted across the {{ agentTotals.agentsWithData }} agents with data in the last 14 days.
            </TooltipContent>
          </Tooltip>
        </span>
        <span class="ix-kpi" :class="agentTotals.errorRate > AGENT_ERROR_BAND_PCT ? 'text-warn' : 'text-fg-1'">
          {{ formatAgentPercent(agentTotals.errorRate) }}
        </span>
        <span class="truncate text-xs leading-4 text-fg-3">Band ≤ 2.0% · {{ errorAgentsAbove }} agents above</span>
      </div>

      <div class="flex min-w-0 flex-col justify-center gap-0.5 px-3 py-2.5">
        <span class="flex items-center gap-1 text-xs leading-4 text-fg-3">
          Spend
          <Tooltip :delay-duration="150">
            <TooltipTrigger as-child>
              <span tabindex="0" class="cursor-help text-fg-3" aria-label="How this is computed">ⓘ</span>
            </TooltipTrigger>
            <TooltipContent side="top" class="!max-w-64 !text-xs !tabular-nums">
              Exact: {{ formatAgentMoney(agentTotals.spendUsd) }} for the {{ "last 14 days" }}, across agents with data.
            </TooltipContent>
          </Tooltip>
        </span>
        <span class="ix-kpi text-fg-1">{{ formatAgentMoney(agentTotals.spendUsd) }}</span>
        <span class="truncate text-xs leading-4 text-fg-3">{{ agentTotals.underBudgetFloor }} {{ agentTotals.underBudgetFloor === 1 ? "agent" : "agents" }} under budget floor</span>
      </div>

      <div class="flex min-w-0 flex-col justify-center gap-0.5 px-3 py-2.5">
        <span class="text-xs leading-4 text-fg-3">Runs</span>
        <span class="ix-kpi text-fg-1">{{ formatAgentCount(agentTotals.runs) }}</span>
        <span class="truncate text-xs leading-4 text-fg-3">across {{ agentTotals.agentsWithData }} agents with data</span>
      </div>
    </section>

    <!-- Toolbar -->
    <div class="flex flex-col gap-2">
      <div class="flex flex-wrap items-center gap-2">
        <div class="relative min-w-52 flex-1 sm:max-w-xs">
          <Search :size="13" :stroke-width="1.9" class="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-fg-3" aria-hidden="true" />
          <input
            ref="searchInput"
            :value="searchDraft"
            type="search"
            placeholder="Search agents, owners, models"
            aria-label="Search agents"
            class="ix-input h-8 pr-9 pl-8 text-xs"
            @input="onSearchInput(($event.target as HTMLInputElement).value)"
            @change="submitSearch"
          >
          <span class="pointer-events-none absolute inset-y-0 right-2 flex items-center"><MemoryKbd>/</MemoryKbd></span>
        </div>

        <div class="flex flex-wrap items-center rounded-lg border border-line-subtle bg-surface-1 p-0.5" role="group" aria-label="Quick filters">
          <button
            v-for="view in AGENT_VIEWS"
            :key="view"
            type="button"
            class="inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            :class="state.view === view ? 'bg-surface-2 text-fg-1 outline outline-1 outline-line-strong' : 'text-fg-3 hover:text-fg-1'"
            :aria-pressed="state.view === view"
            @click="setView(view)"
          >
            {{ AGENT_VIEW_LABELS[view] }}
            <span class="font-mono text-[0.625rem] text-fg-3 tabular-nums">{{ viewCounts[view] }}</span>
          </button>
        </div>

        <div class="flex items-center gap-2 sm:ml-auto">
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <button
                type="button"
                class="inline-flex h-8 items-center gap-1.5 rounded-md border border-line-subtle bg-surface-1 px-2.5 text-xs text-fg-2 transition-colors hover:border-line hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                aria-label="Sort agents"
              >
                Sort: {{ AGENT_SORT_LABELS[state.sort] }}
                <ArrowUp v-if="state.direction === 'asc'" :size="11" :stroke-width="2" class="text-fg-3" aria-hidden="true" />
                <ArrowDown v-else :size="11" :stroke-width="2" class="text-fg-3" aria-hidden="true" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" class="w-48 p-1.5">
              <DropdownMenuLabel class="px-2 py-1.5 text-xs font-semibold text-fg-1">Sort by</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                v-for="key in AGENT_SORT_KEYS"
                :key="key"
                class="justify-between py-1.5 text-xs"
                @select="update({ sort: key, direction: AGENT_DEFAULT_SORT_DIRECTION[key] })"
              >
                {{ AGENT_SORT_LABELS[key] }}
                <span v-if="state.sort === key" class="font-mono text-[0.625rem] text-fg-3">{{ state.direction === "asc" ? "asc" : "desc" }}</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <button
                type="button"
                class="inline-flex h-8 items-center gap-1.5 rounded-md border border-line-subtle bg-surface-1 px-2.5 text-xs text-fg-2 transition-colors hover:border-line hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                aria-label="Group agents"
              >
                Group: {{ AGENT_GROUP_LABELS[state.group] }}
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" class="w-40 p-1.5">
              <DropdownMenuItem
                v-for="key in AGENT_GROUP_KEYS"
                :key="key"
                class="py-1.5 text-xs"
                @select="update({ group: key as AgentGroupKey })"
              >
                {{ AGENT_GROUP_LABELS[key] }}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <div class="flex items-center rounded-md border border-line-subtle bg-surface-1 p-0.5" role="group" aria-label="Row density">
            <button
              type="button"
              class="inline-flex size-6 items-center justify-center rounded transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
              :class="state.density === 'comfortable' ? 'bg-surface-2 text-fg-1' : 'text-fg-3 hover:text-fg-1'"
              aria-label="Comfortable density (52px rows)"
              :aria-pressed="state.density === 'comfortable'"
              @click="update({ density: 'comfortable' })"
            >
              <Rows3 :size="12" :stroke-width="1.9" aria-hidden="true" />
            </button>
            <button
              type="button"
              class="inline-flex size-6 items-center justify-center rounded font-mono text-[0.625rem] transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
              :class="state.density === 'compact' ? 'bg-surface-2 text-fg-1' : 'text-fg-3 hover:text-fg-1'"
              aria-label="Compact density (40px rows)"
              :aria-pressed="state.density === 'compact'"
              @click="update({ density: 'compact' })"
            >
              ≡
            </button>
          </div>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <AgentMultiFilter
          ref="statusFilterRef"
          :label="'Status'"
          :options="statusOptions"
          :model-value="state.statuses"
          @update:model-value="update({ statuses: $event as AgentListState['statuses'] })"
        />
        <AgentMultiFilter
          label="Environment"
          :options="envOptions"
          :model-value="state.envs"
          @update:model-value="update({ envs: $event as AgentListState['envs'] })"
        />
        <AgentMultiFilter
          label="Model"
          :options="options.models"
          :model-value="state.models"
          @update:model-value="update({ models: $event })"
        />
        <AgentMultiFilter
          label="Owner"
          :options="options.owners"
          :model-value="state.owners"
          @update:model-value="update({ owners: $event })"
        />
        <AgentMultiFilter
          label="Health"
          :options="healthOptions"
          :model-value="state.healths"
          @update:model-value="update({ healths: $event as AgentListState['healths'] })"
        />

        <div v-if="chips.length" class="flex flex-wrap items-center gap-1.5">
          <span
            v-for="chip in chips"
            :key="chip.key"
            class="inline-flex h-6 items-center gap-1 rounded-full border border-line bg-raised pr-1 pl-2 text-xs text-fg-2"
          >
            <span class="text-fg-3">{{ chip.field }}:</span> {{ chip.value }}
            <button
              type="button"
              class="inline-flex size-4 items-center justify-center rounded-full text-fg-3 hover:bg-surface-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
              :aria-label="`Remove ${chip.field} filter ${chip.value}`"
              @click="update(chip.next)"
            >
              <X :size="10" :stroke-width="2" aria-hidden="true" />
            </button>
          </span>
          <button
            type="button"
            class="text-xs text-fg-3 underline-offset-2 hover:text-fg-1 hover:underline"
            @click="update(EMPTY_FILTERS)"
          >
            Clear all
          </button>
        </div>

        <div class="ml-auto flex shrink-0 items-center gap-2 text-[0.6875rem] leading-4 text-fg-3">
          <span>
            Showing <span class="font-mono text-fg-2 tabular-nums">{{ filtered.length }}</span> of
            <span class="font-mono text-fg-2 tabular-nums">{{ totalAll }}</span>
          </span>
          <template v-if="noDataHidden">
            <span aria-hidden="true">·</span>
            <span>{{ noDataHidden }} have no data in this period</span>
            <button
              type="button"
              class="rounded text-fg-2 underline decoration-line-strong underline-offset-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
              @click="update({ includeNoData: true })"
            >
              Show them
            </button>
          </template>
          <template v-else>
            <span aria-hidden="true">·</span>
            <button
              type="button"
              class="rounded text-fg-2 underline decoration-line-strong underline-offset-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
              @click="update({ includeNoData: false })"
            >
              Hide agents without data
            </button>
          </template>
        </div>
      </div>
    </div>

    <!-- Table (≥1280px) -->
    <div class="hidden overflow-hidden rounded-lg border border-line-subtle bg-surface min-[1280px]:block">
      <div class="ix-scroll overflow-x-auto">
        <table class="ix-agent-table" :data-density="state.density" aria-label="Agent table">
          <thead>
            <tr>
              <th scope="col" class="ix-agent-sticky !pl-4" :aria-sort="ariaSort('name')">
                <button type="button" class="ix-sort-button" @click="toggleSort('name')">
                  Agent
                  <component :is="sortIcon('name')" :size="10" :stroke-width="2" :class="state.sort === 'name' ? 'text-fg-2' : 'text-fg-off'" aria-hidden="true" />
                </button>
              </th>
              <th scope="col" class="w-36" :aria-sort="ariaSort('health')">
                <button type="button" class="ix-sort-button" @click="toggleSort('health')">
                  Health
                  <component :is="sortIcon('health')" :size="10" :stroke-width="2" :class="state.sort === 'health' ? 'text-fg-2' : 'text-fg-off'" aria-hidden="true" />
                </button>
              </th>
              <th scope="col" class="hidden w-24 min-[1024px]:table-cell">Status</th>
              <th scope="col" class="hidden w-24 min-[1420px]:table-cell">Environment</th>
              <th scope="col" class="hidden w-28 min-[1120px]:table-cell" :aria-sort="ariaSort('lastRun')">
                <button type="button" class="ix-sort-button" @click="toggleSort('lastRun')">
                  Last run
                  <component :is="sortIcon('lastRun')" :size="10" :stroke-width="2" :class="state.sort === 'lastRun' ? 'text-fg-2' : 'text-fg-off'" aria-hidden="true" />
                </button>
              </th>
              <th scope="col" class="w-20 text-right" :aria-sort="ariaSort('runs')">
                <button type="button" class="ix-sort-button ml-auto flex-row-reverse" @click="toggleSort('runs')">
                  Runs
                  <component :is="sortIcon('runs')" :size="10" :stroke-width="2" :class="state.sort === 'runs' ? 'text-fg-2' : 'text-fg-off'" aria-hidden="true" />
                </button>
              </th>
              <th scope="col" class="w-28 text-right" :aria-sort="ariaSort('errors')">
                <button type="button" class="ix-sort-button ml-auto flex-row-reverse" @click="toggleSort('errors')">
                  Error rate
                  <component :is="sortIcon('errors')" :size="10" :stroke-width="2" :class="state.sort === 'errors' ? 'text-fg-2' : 'text-fg-off'" aria-hidden="true" />
                </button>
              </th>
              <th scope="col" class="hidden w-20 text-right min-[1620px]:table-cell" :aria-sort="ariaSort('p95')">
                <button type="button" class="ix-sort-button ml-auto flex-row-reverse" @click="toggleSort('p95')">
                  p95
                  <component :is="sortIcon('p95')" :size="10" :stroke-width="2" :class="state.sort === 'p95' ? 'text-fg-2' : 'text-fg-off'" aria-hidden="true" />
                </button>
              </th>
              <th scope="col" class="w-40" :aria-sort="ariaSort('budget')">
                <button type="button" class="ix-sort-button" @click="toggleSort('budget')">
                  Budget
                  <component :is="sortIcon('budget')" :size="10" :stroke-width="2" :class="state.sort === 'budget' ? 'text-fg-2' : 'text-fg-off'" aria-hidden="true" />
                </button>
              </th>
              <th scope="col" class="hidden w-24 text-right min-[1620px]:table-cell" :aria-sort="ariaSort('coverage')">
                <button type="button" class="ix-sort-button ml-auto flex-row-reverse" @click="toggleSort('coverage')">
                  Coverage
                  <component :is="sortIcon('coverage')" :size="10" :stroke-width="2" :class="state.sort === 'coverage' ? 'text-fg-2' : 'text-fg-off'" aria-hidden="true" />
                </button>
              </th>
              <th scope="col" class="hidden w-28 min-[1620px]:table-cell">Drift</th>
              <th scope="col" class="w-10"><span class="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="group in grouped" :key="group.key">
              <tr v-if="state.group !== 'none'" data-group="true">
                <td colspan="11" class="!pl-4">
                  <span class="flex items-center gap-2 text-xs font-medium text-fg-2">
                    {{ group.label }}
                    <span class="font-mono text-[0.625rem] text-fg-3 tabular-nums">{{ group.agents.length }}</span>
                    <span v-if="group.attentionCount" class="inline-flex items-center gap-1 text-warn">
                      <TriangleAlert :size="11" :stroke-width="1.9" aria-hidden="true" />
                      {{ group.attentionCount }} need attention
                    </span>
                  </span>
                </td>
              </tr>
              <tr
                v-for="agent in group.agents"
                :key="agent.id"
                :data-agent-row="agent.id"
                :data-edge="agentRowEdge(agent) ?? undefined"
                :data-selected="selectedId === agent.id"
                tabindex="0"
                :aria-label="`Open ${agent.name}`"
                @click="openAgent(agent, $event)"
                @keydown="onRowKeydown($event, agent)"
                @mouseenter="onRowEnter(agent, $event)"
                @mouseleave="onRowLeave"
              >
                <td class="ix-agent-sticky !pl-4">
                  <NuxtLink
                    :to="agentHref(agent)"
                    class="block max-w-80 truncate text-sm font-medium text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                    @click.stop
                  >
                    {{ agent.name }}
                  </NuxtLink>
                  <span class="mt-0.5 flex min-w-0 items-center gap-1.5 font-mono text-[0.6875rem] leading-4 text-fg-3">
                    <BrandIcon :id="agent.provider" :size="12" :label="`${agentProviderLabel(agent.provider)} logo`" />
                    <span class="truncate">Agent v{{ agent.agentVersion }} · {{ agent.model }} · {{ agent.owner }}</span>
                  </span>
                </td>
                <td>
                  <AgentHealthDot :health="agent.health" :reasons="agent.healthReasons" />
                </td>
                <td class="hidden min-[1024px]:table-cell">
                  <AgentStatusPill v-if="agent.status !== 'active'" :status="agent.status" :draining-count="agent.stats.activeSessions" />
                  <span v-else class="text-xs text-fg-3">Active</span>
                </td>
                <td class="hidden min-[1420px]:table-cell">
                  <AgentEnvTag :env="agent.env" />
                </td>
                <td class="hidden min-[1120px]:table-cell">
                  <Tooltip v-if="agent.stats.lastRun" :delay-duration="150">
                    <TooltipTrigger as-child>
                      <span
                        class="inline-flex items-center gap-1 text-xs whitespace-nowrap"
                        :class="agent.stats.lastRun.status === 'failed' ? 'text-crit' : 'text-fg-2'"
                      >
                        <CircleSlash v-if="agent.stats.lastRun.status === 'failed'" :size="11" :stroke-width="2" aria-hidden="true" />
                        {{ formatAgentRelative(agent.stats.lastRun.at) }}
                      </span>
                    </TooltipTrigger>
                    <TooltipContent side="top" class="!font-mono !text-xs">
                      {{ formatAgentStamp(agent.stats.lastRun.at) }} · {{ agent.stats.lastRun.status }}
                    </TooltipContent>
                  </Tooltip>
                  <span v-else class="text-xs text-fg-3">Never run</span>
                </td>
                <td class="text-right font-mono text-xs text-fg-1 tabular-nums">{{ formatAgentCount(agent.stats.runs) }}</td>
                <td class="text-right">
                  <AgentMetricCell
                    :value="formatAgentPercent(agent.stats.errorRate)"
                    :over="(agent.stats.errorRate ?? 0) > agent.errorBandPct"
                    :threshold="`Band ≤ ${formatAgentPercent(agent.errorBandPct)}`"
                    :tone="agent.health === 'failing' ? 'destructive' : 'default'"
                  />
                </td>
                <td class="hidden text-right font-mono text-xs min-[1620px]:table-cell">
                  <span
                    :class="
                      agent.stats.p95Ms !== null && agent.latencyBudgetMs !== null && agent.stats.p95Ms > agent.latencyBudgetMs
                        ? 'text-warn'
                        : 'text-fg-1'
                    "
                    :title="agent.latencyBudgetMs !== null ? `Latency budget ${agent.latencyBudgetMs} ms` : undefined"
                  >
                    {{ agent.stats.p95Ms === null ? "Not reported" : `${(agent.stats.p95Ms / 1000).toFixed(1)}s` }}
                  </span>
                </td>
                <td>
                  <div v-if="agent.budget" class="flex items-center gap-2">
                    <div class="w-16 shrink-0">
                      <AgentBudgetBar :budget="agent.budget" size="sm" :show-label="false" />
                    </div>
                    <span
                      class="font-mono text-xs whitespace-nowrap tabular-nums"
                      :class="agentIsNearBudget(agent) ? 'text-warn' : 'text-fg-2'"
                    >
                      {{ formatAgentMoney(agentBudgetLeftUsd(agent.budget)) }} left
                    </span>
                  </div>
                  <span v-else class="text-xs text-fg-3">No budget</span>
                </td>
                <td class="hidden text-right min-[1620px]:table-cell">
                  <Tooltip v-if="agent.stats.coveragePct !== null" :delay-duration="150">
                    <TooltipTrigger as-child>
                      <span
                        class="block font-mono text-xs tabular-nums"
                        :class="agent.stats.coveragePct < agent.coverageTargetPct ? 'text-warn' : 'text-fg-1'"
                      >
                        {{ formatAgentPercent(agent.stats.coveragePct, 0) }}
                      </span>
                    </TooltipTrigger>
                    <TooltipContent side="top" class="!font-mono !text-xs !tabular-nums">
                      {{ formatAgentPercent(agent.stats.coveragePct, 0) }} · {{ formatAgentCount(agent.stats.coverageRuns ?? 0) }} of
                      {{ formatAgentCount(agent.stats.coverageTotal ?? 0) }} runs traced · target {{ agent.coverageTargetPct }}%
                    </TooltipContent>
                  </Tooltip>
                  <span v-else class="text-xs text-fg-3">Not reported</span>
                </td>
                <td class="hidden min-[1620px]:table-cell">
                  <span v-if="agent.drift === 'drifted'" class="inline-flex items-center gap-1 text-xs font-medium text-warn">
                    <TriangleAlert :size="11" :stroke-width="1.9" aria-hidden="true" /> Drifted
                  </span>
                  <span v-else-if="agent.drift === 'watch'" class="inline-flex items-center gap-1 text-xs text-warn">
                    <CircleSlash :size="11" :stroke-width="1.9" aria-hidden="true" /> Watch
                  </span>
                  <span v-else-if="agent.drift === 'not_checked'" class="text-xs text-fg-3">Not checked</span>
                  <Tooltip v-else :delay-duration="150">
                    <TooltipTrigger as-child>
                      <span class="block text-xs text-fg-3" tabindex="0">—</span>
                    </TooltipTrigger>
                    <TooltipContent side="top" class="!text-xs">Drift check ran and found no advisory</TooltipContent>
                  </Tooltip>
                </td>
                <td class="text-right">
                  <DropdownMenu>
                    <DropdownMenuTrigger as-child>
                      <button
                        type="button"
                        class="inline-flex size-6 items-center justify-center rounded text-fg-3 opacity-0 transition-opacity hover:bg-raised hover:text-fg-1 focus-visible:opacity-100 group-hover:opacity-100"
                        :aria-label="`Actions for ${agent.name}`"
                        @click.stop
                      >
                        <Ellipsis :size="14" :stroke-width="1.9" aria-hidden="true" />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" class="w-56 p-1.5" @click.stop>
                      <DropdownMenuItem class="gap-2 py-1.5 text-xs" @select="openAgent(agent)">
                        <ExternalLink :size="13" :stroke-width="1.9" aria-hidden="true" /> Open agent
                      </DropdownMenuItem>
                      <DropdownMenuItem class="gap-2 py-1.5 text-xs" @select="openAgent(agent, { metaKey: true } as MouseEvent)">
                        <ArrowUpRight :size="13" :stroke-width="1.9" aria-hidden="true" /> Open in new tab
                      </DropdownMenuItem>
                      <DropdownMenuItem class="gap-2 py-1.5 text-xs" @select="openQuickLook(agent)">
                        <Search :size="13" :stroke-width="1.9" aria-hidden="true" /> Quick look
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem class="gap-2 py-1.5 text-xs" @select="copyText(agent.id)">
                        <Copy :size="13" :stroke-width="1.9" aria-hidden="true" /> Copy ID
                      </DropdownMenuItem>
                      <DropdownMenuItem class="gap-2 py-1.5 text-xs" @select="copyText(`${currentOrigin()}/agents/${agent.id}`)">
                        <Link2 :size="13" :stroke-width="1.9" aria-hidden="true" /> Copy link
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem disabled class="gap-2 py-1.5 text-xs" title="Read-only console. Requires a privileged write contract.">
                        <Pause :size="13" :stroke-width="1.9" aria-hidden="true" /> Pause
                        <Lock class="ml-auto" :size="11" :stroke-width="1.75" aria-hidden="true" />
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </td>
              </tr>
            </template>
            <tr v-if="!filtered.length">
              <td colspan="11" class="!h-36 text-center">
                <p class="text-sm font-medium text-fg-1">No agents match these filters.</p>
                <p class="mt-1 text-xs text-fg-3">Search and five filters apply to the full agent inventory.</p>
                <button type="button" class="ix-button-secondary mt-3 h-8 text-xs" @click="update(EMPTY_FILTERS)">
                  Clear filters
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Card list (<1280px) -->
    <ul class="grid grid-cols-1 gap-2 sm:grid-cols-2 min-[1280px]:hidden" aria-label="Agent cards">
      <li v-for="agent in filtered" :key="agent.id">
        <NuxtLink
          :to="agentHref(agent)"
          class="flex min-w-0 flex-col gap-1.5 rounded-lg border border-line-subtle bg-surface p-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        >
          <div class="flex min-w-0 items-center justify-between gap-2">
            <span class="min-w-0 truncate text-sm font-medium text-fg-1">{{ agent.name }}</span>
            <AgentHealthDot :health="agent.health" :reasons="agent.healthReasons" />
          </div>
          <div class="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[0.6875rem] text-fg-3 tabular-nums">
            <span>{{ formatAgentCount(agent.stats.runs) }} runs</span>
            <span :class="(agent.stats.errorRate ?? 0) > agent.errorBandPct ? 'text-warn' : ''">
              {{ formatAgentPercent(agent.stats.errorRate) }} errors
            </span>
            <span>{{ agent.budget ? `${formatAgentMoney(agentBudgetLeftUsd(agent.budget))} left` : "No budget" }}</span>
            <span v-if="agent.status !== 'active'" class="text-fg-2">{{ agentStatusLabel(agent.status) }}</span>
          </div>
        </NuxtLink>
      </li>
      <li v-if="!filtered.length" class="rounded-lg border border-dashed border-line px-4 py-6 text-center">
        <p class="text-sm font-medium text-fg-1">No agents match these filters.</p>
        <button type="button" class="ix-button-secondary mt-3 h-8 text-xs" @click="update(EMPTY_FILTERS)">
          Clear filters
        </button>
      </li>
    </ul>

    <!-- Attention sheet: every item, grouped by agent. -->
    <Sheet v-model:open="attentionSheetOpen">
      <SheetContent side="right" class="w-[min(30rem,100vw)] overflow-y-auto sm:max-w-[30rem]">
        <SheetHeader class="gap-1">
          <SheetTitle class="flex items-center gap-2 text-base">
            <TriangleAlert :size="15" :stroke-width="1.9" class="text-warn" aria-hidden="true" />
            {{ attentionCount }} agents need attention
          </SheetTitle>
          <SheetDescription class="text-xs text-fg-3">
            Sorted by severity, then most recent. Every item links to the tab and filter that proves it.
          </SheetDescription>
        </SheetHeader>
        <div class="mt-4 flex flex-col gap-4">
          <section v-for="group in attentionGroups" :key="group.agent.id" class="min-w-0">
            <NuxtLink
              :to="agentHref(group.agent)"
              class="flex items-center justify-between gap-2 rounded-md px-1 py-1 text-sm font-medium text-fg-1 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
            >
              <span class="min-w-0 truncate">{{ group.agent.name }}</span>
              <AgentHealthDot :health="group.agent.health" :reasons="group.agent.healthReasons" size="sm" />
            </NuxtLink>
            <ul class="mt-1 flex flex-col gap-1.5 border-t border-line-subtle pt-2">
              <li v-for="item in group.items" :key="item.id">
                <AgentAttentionItem :item="item" :show-agent="false" :href="agentAttentionHref(item, returnTo)" />
              </li>
            </ul>
          </section>
        </div>
      </SheetContent>
    </Sheet>

    <!-- Quick look: hover or Space, no URL change. -->
    <Sheet :open="quickLookOpen" @update:open="closeQuickLook">
      <SheetContent side="right" class="w-[420px] overflow-y-auto sm:max-w-[420px] !p-0">
        <SheetHeader class="!p-0">
          <SheetTitle class="sr-only">Agent quick look</SheetTitle>
          <SheetDescription class="sr-only">A preview of the selected agent. Open the agent page for every tab.</SheetDescription>
        </SheetHeader>
        <AgentQuickLook
          v-if="quickLookAgent"
          :agent-id="quickLookAgent.id"
          :return-to="returnTo"
          @open="openAgent(quickLookAgent)"
        />
      </SheetContent>
    </Sheet>

    <dialog
      ref="shortcutsDialog"
      class="w-[min(26rem,calc(100vw-1.5rem))] max-w-none rounded-lg border border-line bg-overlay p-0 text-fg-1 shadow-2xl backdrop:bg-canvas/70"
      aria-labelledby="agent-shortcuts-title"
      @click="($event.target === shortcutsDialog) && shortcutsDialog?.close()"
    >
      <div class="flex items-start justify-between gap-3 border-b border-line-subtle px-4 py-3">
        <div>
          <p id="agent-shortcuts-title" class="text-sm font-semibold text-fg-1">Keyboard shortcuts</p>
          <p class="mt-0.5 text-xs text-fg-3">Agents list</p>
        </div>
        <button type="button" class="inline-flex size-7 items-center justify-center rounded-md text-fg-3 hover:bg-surface-2 hover:text-fg-1" aria-label="Close shortcuts" @click="shortcutsDialog?.close()">
          <X :size="15" :stroke-width="1.8" aria-hidden="true" />
        </button>
      </div>
      <dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 p-4 text-xs">
        <dt><MemoryKbd>/</MemoryKbd></dt><dd class="text-fg-2">Focus search</dd>
        <dt><MemoryKbd>J</MemoryKbd> <MemoryKbd>K</MemoryKbd></dt><dd class="text-fg-2">Move the selection</dd>
        <dt><MemoryKbd>Enter</MemoryKbd></dt><dd class="text-fg-2">Open the selected agent</dd>
        <dt><MemoryKbd>Space</MemoryKbd></dt><dd class="text-fg-2">Quick look</dd>
        <dt><MemoryKbd>F</MemoryKbd></dt><dd class="text-fg-2">Focus the filters</dd>
        <dt><MemoryKbd>Esc</MemoryKbd></dt><dd class="text-fg-2">Close the sheet or clear search</dd>
        <dt><MemoryKbd>?</MemoryKbd></dt><dd class="text-fg-2">This sheet</dd>
      </dl>
    </dialog>
  </div>
</template>

<style scoped>
tr[data-group="true"] {
  cursor: default;
}

tr[data-group="true"]:hover td {
  background: color-mix(in srgb, var(--ix-raised) 70%, transparent);
}
</style>
