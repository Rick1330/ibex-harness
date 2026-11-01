<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import {
  ArrowDown,
  ArrowUpRight,
  Check,
  Columns3,
  Copy,
  Search,
  SearchX,
  SlidersHorizontal,
  X,
} from "@lucide/vue"
import SessionsFilters from "./SessionsFilters.vue"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  SESSION_DURATION_LABELS,
  SESSION_ENVIRONMENTS,
  SESSION_OUTCOMES,
  SESSION_SORT_LABELS,
  SESSION_TIERS,
  SESSION_VIEW_LABELS,
  SESSION_VIEWS,
  activeSessionFilterCount,
  emptySessionListState,
  filterSessions,
  hasSessionFilters,
  parseSessionListQuery,
  serializeSessionListQuery,
  sortSessions,
  type SessionEnvironment,
  type SessionHideableColumn,
  type SessionListState,
  type SessionOutcome,
  type SessionSortKey,
} from "@/lib/session-list-query"
import { previewSessions } from "@/lib/session-preview"

const sessions = previewSessions
const route = useRoute()
const router = useRouter()
const state = ref<SessionListState>(parseSessionListQuery(route.query))

const views = SESSION_VIEWS.map((key) => ({ key, label: SESSION_VIEW_LABELS[key] }))
const environments = SESSION_ENVIRONMENTS.map((label) => ({
  label,
  count: sessions.filter((session) => session.env === label).length,
}))
const outcomes = SESSION_OUTCOMES.map((label) => ({
  label,
  count: sessions.filter((session) => session.outcome === label).length,
}))
const agents = [...new Set(sessions.map((session) => session.agent))]

const columnOptions: Array<{ key: SessionHideableColumn; label: string; hint: string }> = [
  { key: "id", label: "Session ID", hint: "Secondary line under the title" },
  { key: "turns", label: "Turns", hint: "Turn count per session" },
  { key: "coverage", label: "Coverage", hint: "Evidence coverage reported" },
  { key: "cost", label: "Cost & tokens", hint: "Session spend and token mix" },
]

const filteredSessions = computed(() => sortSessions(filterSessions(sessions, state.value), state.value.sort, state.value.direction))
const filterCount = computed(() => activeSessionFilterCount(state.value))
const filtersActive = computed(() => hasSessionFilters(state.value))
const resultNoun = computed(() => (filteredSessions.value.length === 1 ? "session" : "sessions"))
const tableColumnCount = computed(
  () => 5 + (["turns", "coverage", "cost"] as const).filter((key) => !state.value.hidden.includes(key)).length,
)

const filterDrawer = ref<HTMLDialogElement | null>(null)
const searchInput = ref<HTMLInputElement | null>(null)
const activeRow = ref(-1)
const selectedIds = ref(new Set<string>())
const selectionCopied = ref(false)
const copyTimer = ref<ReturnType<typeof setTimeout> | null>(null)
let syncTimer: ReturnType<typeof setTimeout> | null = null
const SCROLL_KEY = "ibex:sessions:scroll"

const allVisibleSelected = computed(
  () => filteredSessions.value.length > 0 && filteredSessions.value.every((session) => selectedIds.value.has(session.id)),
)

const activeChips = computed<Array<{ key: string; label: string; remove: () => void }>>(() => {
  const chips: Array<{ key: string; label: string; remove: () => void }> = []
  const current = state.value
  if (current.search.trim()) {
    chips.push({ key: "search", label: `Search: ${current.search.trim()}`, remove: () => patch({ search: "" }) })
  }
  if (current.view !== "all") {
    chips.push({ key: "view", label: SESSION_VIEW_LABELS[current.view], remove: () => patch({ view: "all" }) })
  }
  current.environments.forEach((environment) => {
    chips.push({ key: `env-${environment}`, label: environment, remove: () => toggleEnvironment(environment) })
  })
  current.outcomes.forEach((outcome) => {
    chips.push({ key: `outcome-${outcome}`, label: outcome, remove: () => toggleOutcome(outcome) })
  })
  if (current.tier) chips.push({ key: "tier", label: current.tier, remove: () => patch({ tier: "" }) })
  if (current.agent) chips.push({ key: "agent", label: current.agent, remove: () => patch({ agent: "" }) })
  if (current.id) chips.push({ key: "id", label: current.id, remove: () => patch({ id: "" }) })
  if (current.duration) {
    chips.push({
      key: "duration",
      label: SESSION_DURATION_LABELS[current.duration],
      remove: () => patch({ duration: "" }),
    })
  }
  return chips
})

function patch(partial: Partial<SessionListState>): void {
  state.value = { ...state.value, ...partial }
}

function toggleEnvironment(label: SessionEnvironment): void {
  const current = state.value.environments
  patch({
    environments: current.includes(label) ? current.filter((value) => value !== label) : [...current, label],
  })
}

function toggleOutcome(label: SessionOutcome): void {
  const current = state.value.outcomes
  patch({
    outcomes: current.includes(label) ? current.filter((value) => value !== label) : [...current, label],
  })
}

function toggleSort(key: SessionSortKey): void {
  if (state.value.sort === key) {
    patch({ direction: state.value.direction === "asc" ? "desc" : "asc" })
    return
  }
  patch({ sort: key, direction: key === "activity" ? "desc" : "asc" })
}

function ariaSort(key: SessionSortKey): "ascending" | "descending" | "none" {
  if (state.value.sort !== key) return "none"
  return state.value.direction === "asc" ? "ascending" : "descending"
}

function toggleColumn(key: SessionHideableColumn): void {
  const hidden = state.value.hidden
  patch({
    hidden: hidden.includes(key) ? hidden.filter((value) => value !== key) : [...hidden, key],
  })
}

function clearFilters(): void {
  state.value = {
    ...emptySessionListState(),
    hidden: state.value.hidden,
    sort: state.value.sort,
    direction: state.value.direction,
  }
}

function sessionHref(id: string): string {
  return `/sessions/${encodeURIComponent(id)}`
}

function compactUsage(value: string): string {
  return value.replace(/(\d{1,3}(?:,\d{3})+)/g, (match) => {
    const amount = Number(match.replaceAll(",", ""))
    if (amount < 1_000) return match
    if (amount < 10_000) return `${(amount / 1_000).toFixed(1)}k`
    return `${Math.round(amount / 1_000)}k`
  })
}

function envDotClass(env: SessionEnvironment): string {
  if (env === "production") return "bg-ok"
  if (env === "staging") return "bg-warn"
  return "bg-fg-off"
}

function outcomePillClass(outcome: SessionOutcome): string {
  if (outcome === "succeeded") return "ix-status-pill-ok"
  if (outcome === "denied") return "ix-status-pill-warn"
  return "ix-status-pill-crit"
}

function tierClass(tier: string): string {
  if (tier === "T1") return "border-accent/35 bg-accent/10 text-accent"
  if (tier === "T2") return "border-line-subtle bg-raised text-fg-2"
  return "border-line-subtle text-fg-3"
}

function initials(value: string): string {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("")
}

function toggleRow(id: string): void {
  const next = new Set(selectedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedIds.value = next
}

function toggleAll(): void {
  if (allVisibleSelected.value) {
    const next = new Set(selectedIds.value)
    filteredSessions.value.forEach((session) => next.delete(session.id))
    selectedIds.value = next
    return
  }
  const next = new Set(selectedIds.value)
  filteredSessions.value.forEach((session) => next.add(session.id))
  selectedIds.value = next
}

function clearSelection(): void {
  selectedIds.value = new Set()
}

async function copySelectedIds(): Promise<void> {
  try {
    await navigator.clipboard.writeText([...selectedIds.value].join("\n"))
    selectionCopied.value = true
  } catch {
    selectionCopied.value = false
  }
  if (copyTimer.value) clearTimeout(copyTimer.value)
  copyTimer.value = setTimeout(() => {
    selectionCopied.value = false
  }, 1_500)
}

function toggleFilters(): void {
  if (!filterDrawer.value?.open) filterDrawer.value?.showModal()
}

function closeFilters(): void {
  filterDrawer.value?.close()
}

function onFilterBackdrop(event: MouseEvent): void {
  if (event.target === filterDrawer.value) closeFilters()
}

function rememberScroll(): void {
  if (!import.meta.client) return
  sessionStorage.setItem(SCROLL_KEY, JSON.stringify({ y: window.scrollY, at: Date.now() }))
}

function onGlobalKeydown(event: KeyboardEvent): void {
  const target = event.target as HTMLElement | null
  const inField =
    target instanceof HTMLElement &&
    (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable)
  if (event.key === "/" && !inField && !event.metaKey && !event.ctrlKey) {
    event.preventDefault()
    searchInput.value?.focus()
    return
  }
  if (event.key === "Escape") {
    activeRow.value = -1
    if (inField) target?.blur()
    return
  }
  if (inField || event.metaKey || event.ctrlKey || event.altKey) return
  if (event.key !== "j" && event.key !== "k" && event.key !== "Enter") return
  const rows = filteredSessions.value
  if (!rows.length) return
  if (event.key === "Enter") {
    if (activeRow.value < 0) return
    event.preventDefault()
    void router.push(sessionHref(rows[activeRow.value]!.id))
    return
  }
  event.preventDefault()
  const delta = event.key === "j" ? 1 : -1
  activeRow.value = (activeRow.value + delta + rows.length) % rows.length
  const id = rows[activeRow.value]!.id
  void nextTick(() => {
    const row = document.querySelector<HTMLElement>(`[data-session-row="${id}"]`)
    row?.scrollIntoView({ block: "nearest" })
    row?.querySelector<HTMLElement>("a")?.focus()
  })
}

onMounted(() => {
  window.addEventListener("keydown", onGlobalKeydown)

  const raw = sessionStorage.getItem(SCROLL_KEY)
  if (!raw) return
  sessionStorage.removeItem(SCROLL_KEY)
  try {
    const saved = JSON.parse(raw) as { y?: number; at?: number }
    if (typeof saved.y !== "number" || saved.y <= 0) return
    if (typeof saved.at !== "number" || Date.now() - saved.at > 30 * 60_000) return
    void nextTick(() => window.scrollTo({ top: saved.y, behavior: "instant" }))
  } catch {
    sessionStorage.removeItem(SCROLL_KEY)
  }
})

watch(
  state,
  (value) => {
    if (import.meta.server) return
    if (syncTimer) clearTimeout(syncTimer)
    syncTimer = setTimeout(() => {
      const query = Object.fromEntries(serializeSessionListQuery(value))
      void router.replace({ query })
    }, 250)
  },
  { deep: true },
)

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onGlobalKeydown)
  if (syncTimer) clearTimeout(syncTimer)
  if (copyTimer.value) clearTimeout(copyTimer.value)
})
</script>

<template>
  <div class="space-y-3">
    <section class="overflow-hidden rounded-lg border border-line-subtle bg-surface" aria-label="Session list controls">
      <div class="flex flex-wrap items-center gap-2 p-2.5">
        <div class="relative min-w-[12rem] flex-1 max-xl:basis-full">
          <Search
            :size="15"
            :stroke-width="1.75"
            class="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-fg-3"
            aria-hidden="true"
          />
          <input
            ref="searchInput"
            v-model="state.search"
            type="search"
            class="h-9 w-full rounded-md border border-line-subtle bg-canvas/40 pr-3 pl-9 text-sm text-fg-1 transition-colors placeholder:text-fg-3 hover:border-line focus:border-accent focus:outline-none"
            placeholder="Search ID, title, agent, or error code"
            aria-label="Search sessions"
          >
        </div>

        <div class="ix-scroll flex max-w-full items-center gap-0.5 overflow-x-auto rounded-md border border-line-subtle bg-canvas/40 p-0.5 max-xl:order-3 max-xl:w-full" role="group" aria-label="Saved views">
          <button
            v-for="view in views"
            :key="view.key"
            type="button"
            class="inline-flex h-7 shrink-0 items-center gap-1.5 rounded px-2.5 text-xs whitespace-nowrap transition-colors"
            :class="state.view === view.key ? 'border border-accent/35 bg-accent/10 font-medium text-accent' : 'border border-transparent text-fg-2 hover:bg-raised hover:text-fg-1'"
            :aria-pressed="state.view === view.key"
            @click="patch({ view: view.key })"
          >
            <span v-if="state.view === view.key" class="size-1.5 rounded-full bg-current" aria-hidden="true" />
            {{ view.label }}
          </button>
        </div>

        <button
          type="button"
          class="ix-button-secondary h-9 gap-1.5 px-2.5 text-xs"
          :class="filtersActive && 'border-accent/35 text-accent'"
          @click="toggleFilters"
        >
          <SlidersHorizontal :size="14" :stroke-width="1.75" aria-hidden="true" />
          Filters
          <span v-if="filterCount" class="rounded-full bg-accent/15 px-1.5 py-0.5 font-mono text-[0.625rem] leading-none">{{ filterCount }}</span>
        </button>

        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <button type="button" class="ix-button-secondary h-9 gap-1.5 px-2.5 text-xs">
              <Columns3 :size="14" :stroke-width="1.75" aria-hidden="true" />
              Columns
              <span class="rounded bg-canvas px-1 py-0.5 font-mono text-[0.625rem] leading-none text-fg-3">{{ 8 - state.hidden.length }}</span>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" class="w-64 p-1.5">
            <DropdownMenuLabel class="px-2 py-1.5 text-xs font-semibold text-fg-1">Visible columns</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuCheckboxItem
              v-for="column in columnOptions"
              :key="column.key"
              :model-value="!state.hidden.includes(column.key)"
              class="items-start gap-2 py-1.5 text-[0.8125rem]"
              @update:model-value="toggleColumn(column.key)"
            >
              <span class="flex flex-col gap-0.5">
                <span>{{ column.label }}</span>
                <span class="text-[0.6875rem] leading-4 font-normal text-fg-3">{{ column.hint }}</span>
              </span>
            </DropdownMenuCheckboxItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div v-if="activeChips.length" class="flex flex-wrap items-center gap-1.5 border-t border-line-subtle bg-canvas/25 px-2.5 py-2">
        <span class="mr-0.5 text-[0.6875rem] text-fg-3">Active</span>
        <span
          v-for="chip in activeChips"
          :key="chip.key"
          class="ix-filter-chip"
        >
          {{ chip.label }}
          <button type="button" class="ix-filter-chip-remove" :aria-label="`Remove filter ${chip.label}`" @click="chip.remove">
            <X :size="11" :stroke-width="2" aria-hidden="true" />
          </button>
        </span>
        <button type="button" class="ml-1 text-[0.6875rem] text-fg-3 underline underline-offset-2 hover:text-fg-1" @click="clearFilters">
          Clear all
        </button>
      </div>
    </section>

    <section class="min-w-0 overflow-hidden rounded-lg border border-line-subtle bg-surface" aria-label="Session results">
      <div class="flex flex-wrap items-center justify-between gap-2 border-b border-line-subtle px-3.5 py-3">
        <div class="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <p class="text-[0.9375rem] font-semibold text-fg-1">{{ filteredSessions.length }} matching {{ resultNoun }}</p>
          <span class="text-xs text-fg-3">· {{ sessions.length }} recorded</span>
          <span v-if="filtersActive" class="ix-status-pill h-5 min-h-0 px-1.5 text-[0.625rem]">filtered</span>
        </div>
        <p class="flex items-center gap-1.5 text-[0.6875rem] text-fg-3">
          Sorted by {{ SESSION_SORT_LABELS[state.sort] }}
          <ArrowDown
            :size="11"
            :stroke-width="2"
            :class="state.direction === 'asc' && 'rotate-180'"
            aria-hidden="true"
          />
        </p>
      </div>

      <div
        v-if="selectedIds.size > 0"
        class="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-accent/20 bg-accent/[0.06] px-3.5 py-2 text-xs"
        role="status"
      >
        <p class="text-fg-2"><span class="font-mono font-semibold text-fg-1">{{ selectedIds.size }}</span> selected</p>
        <button type="button" class="inline-flex items-center gap-1 rounded px-1 py-0.5 text-fg-2 transition-colors hover:bg-raised hover:text-fg-1" @click="copySelectedIds">
          <Check v-if="selectionCopied" :size="12" :stroke-width="2" class="text-ok" aria-hidden="true" />
          <Copy v-else :size="12" :stroke-width="1.75" aria-hidden="true" />
          {{ selectionCopied ? "Copied" : "Copy IDs" }}
        </button>
        <button type="button" class="ml-auto text-fg-3 transition-colors hover:text-fg-1" @click="clearSelection">Clear selection</button>
      </div>

      <div class="divide-y divide-line-subtle xl:hidden">
        <div
          v-for="session in filteredSessions"
          :key="session.id"
          class="ix-session-card group relative flex gap-2.5 px-3 py-3 transition-colors hover:bg-raised"
          :class="selectedIds.has(session.id) ? 'bg-accent/[0.045]' : ''"
        >
          <input
            type="checkbox"
            class="ix-row-check relative z-10 mt-0.5 size-3.5 shrink-0 rounded border-line accent-[var(--ix-accent)]"
            :checked="selectedIds.has(session.id)"
            :aria-label="`Select ${session.id}`"
            @change="toggleRow(session.id)"
          >
          <div class="min-w-0 flex-1">
            <div class="flex items-start justify-between gap-2">
              <NuxtLink
                :to="sessionHref(session.id)"
                class="ix-session-link group/link min-w-0"
                :title="session.title"
                @click="rememberScroll"
              >
                <span class="block truncate text-[0.875rem] leading-5 font-medium text-fg-1 group-hover/link:text-accent">{{ session.title }}</span>
                <span class="mt-0.5 flex flex-wrap items-center gap-x-1.5 font-mono text-[0.75rem] leading-4 text-fg-3">
                  <span v-if="!state.hidden.includes('id')" class="truncate">{{ session.id }}</span>
                  <span
                    class="inline-flex h-4 shrink-0 items-center rounded border px-1 text-[0.625rem] leading-none"
                    :class="tierClass(session.tier)"
                  >
                    {{ session.tier }}
                  </span>
                </span>
              </NuxtLink>
              <span class="ix-status-pill shrink-0" :class="outcomePillClass(session.outcome)">
                <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />
                {{ session.outcome }}
              </span>
            </div>

            <div class="mt-2 flex items-center gap-x-3 gap-y-1 text-[0.75rem] text-fg-3">
              <span class="flex min-w-0 items-center gap-1.5">
                <span class="ix-avatar ix-avatar-sm" aria-hidden="true">{{ initials(session.agent) }}</span>
                <span class="truncate text-fg-2">{{ session.agent }}</span>
              </span>
              <span class="flex shrink-0 items-center gap-1.5">
                <span class="size-1.5 rounded-full" :class="envDotClass(session.env)" aria-hidden="true" />
                <span class="capitalize">{{ session.env }}</span>
              </span>
            </div>

            <div class="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[0.75rem] text-fg-3">
              <span class="font-mono tabular-nums text-fg-2">{{ session.last }}</span>
              <span class="font-mono tabular-nums">{{ session.duration }}</span>
              <span><span class="font-mono tabular-nums">{{ session.turns }}</span> turns</span>
              <span v-if="!state.hidden.includes('cost')" class="font-mono tabular-nums">{{ session.cost }}</span>
            </div>

            <p v-if="session.error !== '—'" class="mt-1 truncate font-mono text-[0.6875rem] text-crit">{{ session.error }}</p>
          </div>
        </div>

        <div v-if="filteredSessions.length === 0" class="px-3 py-12">
          <div class="flex flex-col items-center justify-center gap-2 text-center">
            <span class="flex size-9 items-center justify-center rounded-full border border-line-subtle bg-raised text-fg-3">
              <SearchX :size="16" :stroke-width="1.75" aria-hidden="true" />
            </span>
            <p class="text-sm font-medium text-fg-1">No sessions match these filters</p>
            <p class="max-w-sm text-xs leading-5 text-fg-3">Clear the search or filters to return to the {{ sessions.length }} illustrative sessions.</p>
            <button type="button" class="ix-button-secondary mt-1 h-7 px-2.5 text-xs" @click="clearFilters">Clear filters</button>
          </div>
        </div>
      </div>

      <div class="hidden overflow-x-clip xl:block">
        <table class="ix-table ix-sessions-table w-full table-fixed" aria-label="Sessions table">
          <thead>
            <tr>
              <th scope="col" class="w-9 pr-1">
                <input
                  type="checkbox"
                  class="ix-row-check size-3.5 rounded border-line accent-[var(--ix-accent)]"
                  :checked="allVisibleSelected"
                  aria-label="Select all visible sessions"
                  @change="toggleAll"
                >
              </th>
              <th scope="col">Session</th>
              <th scope="col" class="w-[10.5rem]">Agent</th>
              <th scope="col" class="w-[7.75rem]">Outcome</th>
              <th scope="col" class="w-[8.5rem]" :aria-sort="ariaSort('activity')">
                <button type="button" class="ix-sessions-sort" @click="toggleSort('activity')">
                  Activity
                  <ArrowDown
                    :size="11"
                    :stroke-width="2"
                    class="ix-sessions-sort-arrow" :class="state.sort === 'activity' && 'is-active'"
                    :style="state.sort === 'activity' && state.direction === 'asc' ? 'transform: rotate(180deg)' : undefined"
                    aria-hidden="true"
                  />
                </button>
              </th>
              <th v-if="!state.hidden.includes('turns')" scope="col" class="w-[4rem]" :aria-sort="ariaSort('turns')">
                <button type="button" class="ix-sessions-sort ml-auto justify-end" @click="toggleSort('turns')">
                  Turns
                  <ArrowDown
                    :size="11"
                    :stroke-width="2"
                    class="ix-sessions-sort-arrow" :class="state.sort === 'turns' && 'is-active'"
                    :style="state.sort === 'turns' && state.direction === 'asc' ? 'transform: rotate(180deg)' : undefined"
                    aria-hidden="true"
                  />
                </button>
              </th>
              <th v-if="!state.hidden.includes('coverage')" scope="col" class="w-[4.75rem] text-right">Coverage</th>
              <th v-if="!state.hidden.includes('cost')" scope="col" class="w-[6.75rem] text-right" :aria-sort="ariaSort('cost')">
                <button type="button" class="ix-sessions-sort ml-auto justify-end" @click="toggleSort('cost')">
                  Cost
                  <ArrowDown
                    :size="11"
                    :stroke-width="2"
                    class="ix-sessions-sort-arrow" :class="state.sort === 'cost' && 'is-active'"
                    :style="state.sort === 'cost' && state.direction === 'asc' ? 'transform: rotate(180deg)' : undefined"
                    aria-hidden="true"
                  />
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="session in filteredSessions"
              :key="session.id"
              :data-session-row="session.id"
              class="ix-session-row group"
              :data-selected="selectedIds.has(session.id)"
            >
              <td class="relative z-10 pr-1">
                <input
                  type="checkbox"
                  class="ix-row-check size-3.5 rounded border-line accent-[var(--ix-accent)]"
                  :checked="selectedIds.has(session.id)"
                  :aria-label="`Select ${session.id}`"
                  @change="toggleRow(session.id)"
                >
              </td>
              <td>
                <NuxtLink
                  :to="sessionHref(session.id)"
                  class="ix-session-link group/link block min-w-0"
                  :title="session.title"
                  @click="rememberScroll"
                >
                  <span class="flex items-center gap-1.5">
                    <span class="truncate text-[0.875rem] leading-5 font-medium text-fg-1 group-hover/link:text-accent">{{ session.title }}</span>
                    <ArrowUpRight :size="12" :stroke-width="1.75" class="ix-session-arrow shrink-0" aria-hidden="true" />
                  </span>
                  <span v-if="!state.hidden.includes('id')" class="mt-0.5 flex items-center gap-1.5 font-mono text-[0.75rem] leading-4 text-fg-3">
                    <span class="truncate">{{ session.id }}</span>
                    <span
                      class="inline-flex h-4 shrink-0 items-center rounded border px-1 text-[0.625rem] leading-none"
                      :class="tierClass(session.tier)"
                    >
                      {{ session.tier }}
                    </span>
                  </span>
                </NuxtLink>
              </td>
              <td>
                <div class="flex min-w-0 items-center gap-2">
                  <span class="ix-avatar ix-avatar-sm" aria-hidden="true">{{ initials(session.agent) }}</span>
                  <div class="min-w-0">
                    <p class="truncate text-[0.8125rem] leading-5 font-medium text-fg-1" :title="session.agent">{{ session.agent }}</p>
                    <p class="flex items-center gap-1.5 text-[0.75rem] leading-4 text-fg-3">
                      <span class="size-1.5 rounded-full" :class="envDotClass(session.env)" aria-hidden="true" />
                      <span class="capitalize">{{ session.env }}</span>
                    </p>
                  </div>
                </div>
              </td>
              <td>
                <span class="ix-status-pill" :class="outcomePillClass(session.outcome)">
                  <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />
                  {{ session.outcome }}
                </span>
                <p v-if="session.error !== '—'" class="mt-1 truncate font-mono text-[0.75rem] leading-4 text-crit" :title="session.error">{{ session.error }}</p>
              </td>
              <td :title="`Last seen ${session.last} · first seen ${session.first}`">
                <p class="font-mono text-[0.8125rem] leading-4 font-medium text-fg-1 tabular-nums">{{ session.last }}</p>
                <p class="mt-0.5 font-mono text-[0.75rem] leading-4 whitespace-nowrap text-fg-3 tabular-nums">{{ session.duration }} <span class="text-fg-off" aria-hidden="true">·</span> {{ session.first }}</p>
              </td>
              <td v-if="!state.hidden.includes('turns')" class="text-right font-mono text-[0.8125rem] text-fg-1 tabular-nums">{{ session.turns }}</td>
              <td
                v-if="!state.hidden.includes('coverage')"
                class="text-right font-mono text-[0.8125rem] whitespace-nowrap tabular-nums"
                :class="session.coverage === '2 / 3' ? 'text-warn' : 'text-fg-1'"
              >
                {{ session.coverage }}
              </td>
              <td v-if="!state.hidden.includes('cost')" class="text-right">
                <p class="font-mono text-[0.8125rem] leading-4 whitespace-nowrap text-fg-1 tabular-nums">{{ session.cost }}</p>
                <p class="mt-0.5 truncate font-mono text-[0.75rem] leading-4 text-fg-3" :title="`${session.cost} · ${session.usage} tokens`">{{ compactUsage(session.usage) }}</p>
              </td>
            </tr>
            <tr v-if="filteredSessions.length === 0">
              <td :colspan="tableColumnCount" class="!h-52">
                <div class="flex flex-col items-center justify-center gap-2 text-center">
                  <span class="flex size-9 items-center justify-center rounded-full border border-line-subtle bg-raised text-fg-3">
                    <SearchX :size="16" :stroke-width="1.75" aria-hidden="true" />
                  </span>
                  <p class="text-sm font-medium text-fg-1">No sessions match these filters</p>
                  <p class="max-w-sm text-xs leading-5 text-fg-3">Clear the search or filters to return to the {{ sessions.length }} illustrative sessions.</p>
                  <button type="button" class="ix-button-secondary mt-1 h-7 px-2.5 text-xs" @click="clearFilters">Clear filters</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="flex flex-wrap items-center justify-between gap-2 border-t border-line-subtle px-3.5 py-2.5 text-[0.6875rem] text-fg-3">
        <p>
          <span class="font-mono text-fg-2 tabular-nums">{{ filteredSessions.length }}</span>
          of
          <span class="font-mono text-fg-2 tabular-nums">{{ sessions.length }}</span>
          illustrative sessions
        </p>
        <p class="flex items-center gap-1.5">
          <span>Page 1 / 1</span>
          <span aria-hidden="true">·</span>
          <span>{{ SESSION_SORT_LABELS[state.sort] }} {{ state.direction === "asc" ? "ascending" : "descending" }}</span>
        </p>
      </div>
    </section>

    <dialog ref="filterDrawer" class="ix-filter-drawer" aria-label="Session filters" @click="onFilterBackdrop">
      <div class="ix-filter-drawer-panel">
        <div class="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-line-subtle px-4">
          <p class="flex items-center gap-1.5 text-sm font-semibold text-fg-1">
            <SlidersHorizontal :size="15" :stroke-width="1.75" class="text-fg-3" aria-hidden="true" />
            Filters
          </p>
          <button type="button" class="ix-drawer-icon" aria-label="Close filters" @click="closeFilters">
            <X :size="16" :stroke-width="1.75" aria-hidden="true" />
          </button>
        </div>
        <div class="ix-scroll min-h-0 flex-1 overflow-y-auto">
          <SessionsFilters
            v-model:state="state"
            :environments="environments"
            :outcomes="outcomes"
            :tiers="SESSION_TIERS"
            :agents="agents"
          />
        </div>
        <div class="flex shrink-0 items-center gap-2 border-t border-line-subtle p-3">
          <button
            type="button"
            class="ix-button-secondary h-9 flex-1 justify-center text-xs"
            :disabled="!filtersActive"
            @click="clearFilters"
          >
            Reset
          </button>
          <button type="button" class="ix-button-primary h-9 flex-1 justify-center text-xs" @click="closeFilters">
            Show {{ filteredSessions.length }} {{ resultNoun }}
          </button>
        </div>
      </div>
    </dialog>
  </div>
</template>

<style scoped>
.ix-filter-chip {
  display: inline-flex;
  height: 1.5rem;
  align-items: center;
  gap: 0.25rem;
  border: 1px solid var(--ix-line-subtle);
  border-radius: 9999px;
  background: var(--ix-surface);
  padding: 0 0.375rem 0 0.5rem;
  font-size: 0.6875rem;
  line-height: 1;
  color: var(--ix-fg-2);
}

.ix-filter-chip-remove {
  display: inline-flex;
  width: 1rem;
  height: 1rem;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  color: var(--ix-fg-3);
  transition: background-color 100ms, color 100ms;
}

.ix-filter-chip-remove:hover {
  background: var(--ix-raised);
  color: var(--ix-fg-1);
}

.ix-session-row,
.ix-session-card {
  position: relative;
}

.ix-session-link::after {
  content: "";
  position: absolute;
  inset: 0;
  z-index: 0;
  border-radius: 4px;
}

.ix-session-link:focus-visible {
  outline: none;
}

.ix-session-link:focus-visible::after {
  outline: 2px solid var(--ix-accent);
  outline-offset: -2px;
}

.ix-session-arrow {
  color: var(--ix-fg-off);
  opacity: 0;
  transform: translateX(-2px);
  transition: opacity 120ms, transform 120ms, color 120ms;
}

.ix-session-row:hover .ix-session-arrow,
.ix-session-link:focus-visible .ix-session-arrow {
  color: var(--ix-fg-2);
  opacity: 1;
  transform: none;
}

.ix-row-check {
  opacity: 0.45;
  transition: opacity 120ms;
}

.ix-row-check:checked,
.ix-row-check:focus-visible,
.ix-session-row:hover .ix-row-check,
.ix-session-card:hover .ix-row-check {
  opacity: 1;
}

.ix-sessions-table th {
  position: sticky;
  top: 3rem;
  z-index: 4;
  height: 2.5rem;
  background: var(--ix-surface);
  font-family: var(--font-sans);
  font-size: 0.75rem;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
  color: var(--ix-fg-2);
  box-shadow: inset 0 -1px 0 var(--ix-line);
}

.ix-sessions-table td {
  height: 3.5rem;
}

.ix-sessions-table .ix-status-pill {
  font-size: 0.75rem;
}

.ix-sessions-sort {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  border-radius: 4px;
  color: inherit;
  transition: color 100ms;
}

.ix-sessions-sort:hover {
  color: var(--ix-fg-1);
}

.ix-sessions-sort:focus-visible {
  outline: 2px solid var(--ix-accent);
  outline-offset: 2px;
}

.ix-sessions-sort-arrow {
  color: var(--ix-fg-off);
  opacity: 0;
  transition: opacity 120ms, color 120ms;
}

.ix-sessions-table th:hover .ix-sessions-sort-arrow,
.ix-sessions-sort:focus-visible .ix-sessions-sort-arrow,
.ix-sessions-sort-arrow.is-active {
  color: var(--ix-fg-1);
  opacity: 1;
}

.ix-filter-drawer {
  width: min(22rem, calc(100vw - 1.5rem));
  max-width: none;
  height: 100dvh;
  max-height: none;
  margin: 0 0 0 auto;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
}

.ix-filter-drawer::backdrop {
  background: rgb(0 0 0 / 0.5);
}

.ix-filter-drawer-panel {
  display: flex;
  height: 100%;
  flex-direction: column;
  border-left: 1px solid var(--ix-line);
  background: var(--ix-overlay);
}

.ix-drawer-icon {
  display: inline-flex;
  width: 2rem;
  height: 2rem;
  align-items: center;
  justify-content: center;
  border-radius: 5px;
  color: var(--ix-fg-3);
}

.ix-drawer-icon:hover {
  background: var(--ix-raised);
  color: var(--ix-fg-1);
}

@media (min-width: 1536px) {
  .ix-filter-drawer {
    display: none;
  }
}
</style>
