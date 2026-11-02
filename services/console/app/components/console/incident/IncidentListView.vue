<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import type { Component } from "vue"
import {
  ArrowDown,
  ArrowUp,
  ChevronRight,
  CircleAlert,
  CircleDot,
  Clock,
  Eye,
  Search,
  Siren,
  TriangleAlert,
  UserRound,
  Wrench,
} from "@lucide/vue"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import AgentMultiFilter from "@/components/console/agent/list/primitives/AgentMultiFilter.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import GovernShortcutsDialog from "@/components/console/govern/primitives/GovernShortcutsDialog.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import KeyHint from "@/components/console/primitives/KeyHint.vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import {
  formatGovernRelative,
  formatGovernStamp,
} from "@/lib/govern-format"
import {
  INCIDENT_DEFAULT_SORT_DIRECTION,
  INCIDENT_SEVERITIES,
  INCIDENT_SORT_LABELS,
  INCIDENT_STATE_LABELS,
  INCIDENT_STATES,
  INCIDENT_VIEW_LABELS,
  INCIDENT_VIEWS,
  formatIncidentAge,
  incidentById,
  incidentMatches,
  incidentOwners,
  incidentSummary,
  incidents,
  isOpenIncident,
  sortIncidents,
  type Incident,
  type IncidentListState,
  type IncidentSeverity,
  type IncidentSortKey,
  type IncidentState,
  type IncidentView,
} from "@/lib/incident-preview"

const props = defineProps<{ state: IncidentListState }>()
const emit = defineEmits<{ update: [state: IncidentListState] }>()

function update(patch: Partial<IncidentListState>): void {
  emit("update", { ...props.state, ...patch })
}

const summary = incidentSummary()

// ---- filtering -----------------------------------------------------------
const filtered = computed(() =>
  sortIncidents(incidents.filter((incident) => incidentMatches(incident, props.state)), props.state.sort, props.state.direction),
)
const openCount = computed(() => incidents.filter(isOpenIncident).length)
const severityCounts = computed(() =>
  Object.fromEntries(INCIDENT_SEVERITIES.map((severity) => [severity, incidents.filter((incident) => isOpenIncident(incident) && incident.severity === severity).length])),
)
const ownerOptions = computed(() => {
  const owners = incidentOwners()
  return owners.map((owner) => ({
    value: owner,
    label: owner,
    count: incidents.filter((incident) => (incident.owner ?? "Unassigned") === owner).length,
  }))
})
const severityOptions = computed(() =>
  INCIDENT_SEVERITIES.map((severity) => ({
    value: severity,
    label: severity,
    count: incidents.filter((incident) => incident.severity === severity).length,
  })),
)
const stateOptions = computed(() =>
  INCIDENT_STATES.map((state) => ({
    value: state,
    label: INCIDENT_STATE_LABELS[state],
    count: incidents.filter((incident) => incident.state === state).length,
  })),
)

const activeFilterCount = computed(
  () => props.state.severities.length + props.state.states.length + props.state.owners.length + (props.state.search ? 1 : 0),
)

function clearFilters(): void {
  update({ search: "", severities: [], states: [], owners: [] })
}

// ---- search --------------------------------------------------------------
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

function focusSearch(): void {
  searchInput.value?.focus()
  searchInput.value?.select()
}

// ---- sorting -------------------------------------------------------------
function toggleSort(key: IncidentSortKey): void {
  if (props.state.sort === key) {
    update({ direction: props.state.direction === "asc" ? "desc" : "asc" })
  } else {
    update({ sort: key, direction: INCIDENT_DEFAULT_SORT_DIRECTION[key] })
  }
}

function ariaSort(key: IncidentSortKey): "ascending" | "descending" | "none" {
  if (props.state.sort !== key) return "none"
  return props.state.direction === "asc" ? "ascending" : "descending"
}

function sortIcon(key: IncidentSortKey) {
  if (props.state.sort !== key) return ArrowUp
  return props.state.direction === "asc" ? ArrowUp : ArrowDown
}

// ---- row presentation ----------------------------------------------------
function severityTone(severity: IncidentSeverity): string {
  if (severity === "SEV-1") return "border-crit/35 bg-crit-tint text-crit"
  if (severity === "SEV-2") return "border-warn/35 bg-warn-tint text-warn"
  if (severity === "SEV-4") return "border-dashed border-line text-fg-3"
  return "border-line bg-raised text-fg-2"
}

function severityDot(severity: IncidentSeverity): string {
  if (severity === "SEV-1") return "bg-crit"
  if (severity === "SEV-2") return "bg-warn"
  return "bg-line-strong"
}

const stateConfig: Record<IncidentState, { icon: Component; tone: string }> = {
  investigating: { icon: CircleDot, tone: "border-warn/35 bg-warn-tint text-warn" },
  identified: { icon: TriangleAlert, tone: "border-warn/35 bg-warn-tint text-warn" },
  mitigating: { icon: Wrench, tone: "border-accent/35 bg-accent-tint text-accent" },
  monitoring: { icon: Eye, tone: "border-line bg-raised text-fg-2" },
  resolved: { icon: CircleDot, tone: "border-transparent bg-transparent text-ok" },
}

function edgeFor(incident: Incident): "critical" | "warning" | undefined {
  if (incident.state === "resolved") return undefined
  if (incident.severity === "SEV-1" || (!incident.acknowledgedAt && incident.severity === "SEV-2")) return "critical"
  if (!incident.acknowledgedAt || !incident.owner) return "warning"
  return undefined
}

function ageOf(incident: Incident): string {
  return formatIncidentAge(incident.startedAt, incident.resolvedAt)
}

function lastUpdate(incident: Incident): string {
  return formatGovernRelative(incident.updatedAt)
}

// ---- detail drawer -------------------------------------------------------
const selected = computed(() => (props.state.incident ? incidentById(props.state.incident) : null))
const detailOpen = computed(() => Boolean(selected.value))

function openIncident(incident: Incident, event?: MouseEvent): void {
  if (event && (event.metaKey || event.ctrlKey || event.shiftKey)) {
    window.open(`/incidents?incident=${incident.id}`, "_blank", "noopener")
    return
  }
  update({ incident: incident.id })
}

function closeDetail(open: boolean): void {
  if (!open) update({ incident: "" })
}

/* Focus the drawer itself, not the first control: focusing the copy button used
   to pop its tooltip over the incident title the moment the drawer opened. */
function focusDrawer(event: Event): void {
  event.preventDefault()
  void nextTick(() => document.querySelector<HTMLElement>('[data-slot="sheet-content"]')?.focus())
}

function onRowKeydown(event: KeyboardEvent, incident: Incident): void {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault()
    openIncident(incident)
  }
}

// ---- keyboard ------------------------------------------------------------
const selectedIndex = ref(-1)
const shortcutsOpen = ref(false)

function moveSelection(delta: number): void {
  if (!filtered.value.length) return
  const next = (selectedIndex.value + delta + filtered.value.length) % filtered.value.length
  selectedIndex.value = next
  void nextTick(() => {
    document.querySelector<HTMLElement>(`[data-incident-row="${filtered.value[next]!.id}"]`)?.focus()
  })
}

function isTypingTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && Boolean(target.closest("input, textarea, select, [contenteditable]"))
}

function onGlobalKeydown(event: KeyboardEvent): void {
  if (event.metaKey || event.ctrlKey || event.altKey) return
  if (isTypingTarget(event.target)) return
  if (event.key === "/") {
    event.preventDefault()
    focusSearch()
  } else if (event.key === "j" || event.key === "J") {
    event.preventDefault()
    moveSelection(1)
  } else if (event.key === "k" || event.key === "K") {
    event.preventDefault()
    moveSelection(-1)
  } else if (event.key === "?") {
    event.preventDefault()
    shortcutsOpen.value = true
  } else if (event.key === "Escape") {
    if (selected.value) update({ incident: "" })
    else if (searchDraft.value) {
      searchDraft.value = ""
      update({ search: "" })
    }
  }
}

onMounted(() => window.addEventListener("keydown", onGlobalKeydown))
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onGlobalKeydown)
  if (searchTimer) clearTimeout(searchTimer)
})

const shortcutGroups = [
  {
    title: "Everywhere",
    rows: [
      { keys: "/", label: "Focus search" },
      { keys: "?", label: "Show this sheet" },
      { keys: "Esc", label: "Close the drawer or clear search" },
    ],
  },
  {
    title: "This page",
    rows: [
      { keys: "j / k", label: "Move between incidents" },
      { keys: "Enter", label: "Open the focused incident" },
      { keys: "Space", label: "Open the focused incident" },
    ],
  },
]


const tiles = computed(() => [
  {
    label: "Open incidents",
    value: String(summary.open),
    helper: `${summary.sev1} SEV-1 · ${summary.sev2} SEV-2`,
    tone: summary.sev1 ? ("critical" as const) : ("default" as const),
  },
  {
    label: "Unacknowledged",
    value: String(summary.unacknowledged),
    helper: summary.unacknowledged ? "No owner has acknowledged" : "Every open incident is acknowledged",
    tone: summary.unacknowledged ? ("warning" as const) : ("default" as const),
  },
  {
    label: "Oldest open",
    value: summary.oldest ? formatIncidentAge(summary.oldest.startedAt, null) : "—",
    helper: summary.oldest ? summary.oldest.title : "No open incidents",
    tone: "default" as const,
  },
  {
    label: "Resolved",
    value: String(summary.resolved),
    helper: "In the 14-day preview window",
    tone: "success" as const,
  },
])

const aboutNotes = [
  {
    lead: "One queue, two windows.",
    body: "The table defaults to open incidents. Resolved incidents stay in the same fixture set so age and resolution can be compared without inventing history.",
  },
  {
    lead: "Severity is not status.",
    body: "Severity says how bad it is (SEV-1…SEV-4). State says where the response is (investigating, identified, mitigating, monitoring, resolved).",
  },
  {
    lead: "Impact is recorded, not guessed.",
    body: "The impact summary is part of the incident record. When the contract lands, affected sessions and runs will join to Explore; this preview does not claim those joins.",
  },
]
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">
    <ConsolePageHeader
      title="Incidents"
      definition="What is broken right now, who owns it, and how far it has spread."
      state="illustrative"
      :verdict="`Preview renders ${incidents.length} illustrative incidents. The incident object contract is not connected, so no live count, owner, or severity is claimed.`"
      contract="operator.incidents.v1 [NEEDS-BACKEND]"
      scope="org_demo_42 · all environments"
      range="Open queue + 14-day resolved window"
      coverage="0% live · illustrative only"
      :notes="aboutNotes"
    >
      <template #actions>
        <GovernLockedAction label="Declare incident" :icon="Siren" variant="primary" />
      </template>
      <div
        class="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs leading-4 text-fg-3"
        role="group"
        aria-label="Filter incidents by state and severity"
      >
        <button
          type="button"
          class="font-mono font-medium text-fg-2 tabular-nums underline-offset-2 hover:text-fg-1 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          @click="update({ view: 'open', severities: [] })"
        >{{ openCount }} open</button>
        <span class="text-fg-off" aria-hidden="true">·</span>
        <button
          v-for="(severity, index) in INCIDENT_SEVERITIES"
          :key="severity"
          type="button"
          class="inline-flex items-center gap-1.5 underline-offset-2 hover:text-fg-1 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          :class="severityCounts[severity] ? 'text-fg-2' : 'text-fg-3'"
          :aria-label="`Filter to ${severityCounts[severity]} open ${severity} incidents`"
          @click="update({ view: 'open', severities: [severity] })"
        >
          <span class="size-1.5 rounded-full" :class="severityDot(severity)" aria-hidden="true" />
          <span class="font-mono tabular-nums">{{ severityCounts[severity] }}</span>
          {{ severity }}
          <span v-if="index < INCIDENT_SEVERITIES.length - 1" class="sr-only">,</span>
        </button>
        <span class="text-fg-off" aria-hidden="true">·</span>
        <button
          type="button"
          class="underline-offset-2 hover:text-fg-1 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          @click="update({ view: 'resolved', severities: [] })"
        >{{ summary.resolved }} resolved</button>
      </div>
    </ConsolePageHeader>

    <section class="grid grid-cols-2 gap-3 xl:grid-cols-4" aria-label="Incident summary">
      <GovernStatTile
        v-for="tile in tiles"
        :key="tile.label"
        :label="tile.label"
        :value="tile.value"
        :helper="tile.helper"
        :tone="tile.tone"
      />
    </section>

    <section class="overflow-hidden rounded-lg border border-line-subtle bg-surface">
      <div class="flex flex-wrap items-center gap-2 border-b border-line-subtle px-3 py-2">
        <div class="relative w-full min-w-0 sm:w-64">
          <Search :size="13" :stroke-width="1.9" class="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-fg-3" aria-hidden="true" />
          <input
            ref="searchInput"
            :value="searchDraft"
            type="search"
            placeholder="Search title, id, service, owner"
            aria-label="Search incidents"
            class="ix-input h-8 pr-9 pl-8 text-xs"
            @input="onSearchInput(($event.target as HTMLInputElement).value)"
            @keydown.enter.prevent="update({ search: searchDraft })"
          >
          <span class="pointer-events-none absolute inset-y-0 right-2 flex items-center"><KeyHint>/</KeyHint></span>
        </div>

        <AgentMultiFilter
          label="Severity"
          :options="severityOptions"
          :model-value="state.severities"
          @update:model-value="update({ severities: $event as IncidentSeverity[] })"
        />
        <AgentMultiFilter
          label="State"
          :options="stateOptions"
          :model-value="state.states"
          @update:model-value="update({ states: $event as IncidentState[] })"
        />
        <AgentMultiFilter
          label="Owner"
          :options="ownerOptions"
          :model-value="state.owners"
          @update:model-value="update({ owners: $event })"
        />

        <GovernFilterSelect
          label="Sort"
          :model-value="state.sort"
          :options="Object.entries(INCIDENT_SORT_LABELS).map(([value, label]) => ({ value, label }))"
          @update:model-value="update({ sort: $event as IncidentSortKey, direction: INCIDENT_DEFAULT_SORT_DIRECTION[$event as IncidentSortKey] })"
        />

        <div class="inline-flex h-8 items-center rounded-full border border-line-subtle bg-surface-1 p-0.5" role="group" aria-label="Incident view">
          <button
            v-for="view in INCIDENT_VIEWS"
            :key="view"
            type="button"
            class="inline-flex h-7 items-center rounded-full px-2.5 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            :class="state.view === view ? 'bg-raised text-fg-1 shadow-sm' : 'text-fg-3 hover:text-fg-1'"
            :aria-pressed="state.view === view"
            @click="update({ view: view as IncidentView })"
          >
            {{ INCIDENT_VIEW_LABELS[view] }}
          </button>
        </div>

        <div class="ml-auto flex items-center gap-2 text-[0.6875rem] leading-4 text-fg-3">
          <span class="font-mono tabular-nums">{{ filtered.length }} of {{ incidents.length }}</span>
          <button
            v-if="activeFilterCount"
            type="button"
            class="rounded px-1 text-xs font-medium text-fg-2 underline decoration-line-strong underline-offset-3 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            @click="clearFilters"
          >Clear filters</button>
        </div>
      </div>

      <div class="overflow-x-auto">
        <table class="ix-list-table min-w-[46rem]" aria-label="Incidents">
          <thead>
            <tr>
              <th scope="col" class="w-24" :aria-sort="ariaSort('severity')">
                <button type="button" class="ix-sort-button" @click="toggleSort('severity')">
                  Severity
                  <component :is="sortIcon('severity')" :size="10" :stroke-width="2" :class="state.sort === 'severity' ? 'text-fg-2' : 'text-fg-off'" aria-hidden="true" />
                </button>
              </th>
              <th scope="col" :aria-sort="ariaSort('title')">
                <button type="button" class="ix-sort-button" @click="toggleSort('title')">
                  Incident
                  <component :is="sortIcon('title')" :size="10" :stroke-width="2" :class="state.sort === 'title' ? 'text-fg-2' : 'text-fg-off'" aria-hidden="true" />
                </button>
              </th>
              <th scope="col" class="hidden w-36 md:table-cell">Owner</th>
              <th scope="col" class="w-20" :aria-sort="ariaSort('started')">
                <button type="button" class="ix-sort-button" @click="toggleSort('started')">
                  Age
                  <component :is="sortIcon('started')" :size="10" :stroke-width="2" :class="state.sort === 'started' ? 'text-fg-2' : 'text-fg-off'" aria-hidden="true" />
                </button>
              </th>
              <th scope="col" class="hidden w-44 lg:table-cell">Impact</th>
              <th scope="col" class="w-32">State</th>
              <th scope="col" class="hidden w-28 text-right xl:table-cell" :aria-sort="ariaSort('updated')">
                <button type="button" class="ix-sort-button ml-auto flex-row-reverse" @click="toggleSort('updated')">
                  Updated
                  <component :is="sortIcon('updated')" :size="10" :stroke-width="2" :class="state.sort === 'updated' ? 'text-fg-2' : 'text-fg-off'" aria-hidden="true" />
                </button>
              </th>
              <th scope="col" class="w-10"><span class="sr-only">Open</span></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="incident in filtered"
              :key="incident.id"
              :data-incident-row="incident.id"
              :data-edge="edgeFor(incident)"
              :data-selected="state.incident === incident.id"
              tabindex="0"
              :aria-label="`Open ${incident.id}: ${incident.title}`"
              @click="openIncident(incident, $event)"
              @keydown="onRowKeydown($event, incident)"
            >
              <td>
                <span class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 font-mono text-[0.6875rem] leading-none font-medium whitespace-nowrap tabular-nums" :class="severityTone(incident.severity)">
                  <span class="size-1.5 rounded-full" :class="severityDot(incident.severity)" aria-hidden="true" />
                  {{ incident.severity }}
                </span>
              </td>
              <td>
                <div class="min-w-0">
                  <p class="truncate text-[0.8125rem] leading-5 font-medium text-fg-1">{{ incident.title }}</p>
                  <p class="mt-0.5 flex items-center gap-1.5 truncate font-mono text-[0.6875rem] leading-4 text-fg-3">
                    <span>{{ incident.id }}</span>
                    <span aria-hidden="true">·</span>
                    <span>{{ incident.service }}</span>
                    <span aria-hidden="true">·</span>
                    <span>{{ incident.env }}</span>
                  </p>
                </div>
              </td>
              <td class="hidden md:table-cell">
                <span v-if="incident.owner" class="flex items-center gap-1.5 text-xs text-fg-2">
                  <UserRound :size="12" :stroke-width="1.8" class="shrink-0 text-fg-3" aria-hidden="true" />
                  {{ incident.owner }}
                </span>
                <span v-else class="inline-flex items-center gap-1.5 text-xs text-warn">
                  <CircleAlert :size="12" :stroke-width="1.9" aria-hidden="true" />
                  Unassigned
                </span>
              </td>
              <td class="font-mono text-xs text-fg-2 tabular-nums" :title="formatGovernStamp(incident.startedAt)">{{ ageOf(incident) }}</td>
              <td class="hidden lg:table-cell">
                <span class="text-xs" :class="incident.impact === 'none' ? 'text-fg-3' : incident.impact === 'partial' ? 'text-crit' : 'text-fg-2'">
                  {{ incident.impactSummary }}
                </span>
              </td>
              <td>
                <span class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-[0.6875rem] leading-none font-medium whitespace-nowrap" :class="stateConfig[incident.state].tone">
                  <component :is="stateConfig[incident.state].icon" :size="11" :stroke-width="2" aria-hidden="true" />
                  {{ INCIDENT_STATE_LABELS[incident.state] }}
                </span>
              </td>
              <td class="hidden text-right text-xs text-fg-3 xl:table-cell" :title="formatGovernStamp(incident.updatedAt)">
                {{ lastUpdate(incident) }}
              </td>
              <td>
                <ChevronRight :size="14" :stroke-width="1.8" class="text-fg-off" aria-hidden="true" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <GovernEmptyState
        v-if="!filtered.length"
        title="No incidents match this view"
        reason="Adjust the severity, state, or owner filters, or switch back to the open queue."
        action-label="Clear filters"
        class="m-3"
        @action="clearFilters"
      />

      <div class="flex flex-wrap items-center justify-between gap-2 border-t border-line-subtle px-4 py-2 text-[0.6875rem] leading-4 text-fg-3">
        <span class="inline-flex items-center gap-1.5">
          <Clock :size="12" :stroke-width="1.8" aria-hidden="true" />
          Ages are relative to the fixture clock; open the drawer for absolute UTC.
        </span>
        <span class="font-mono">Read-only · incident writes need a contract</span>
      </div>
    </section>

    <Sheet :open="detailOpen" @update:open="closeDetail">
      <SheetContent side="right" tabindex="-1" class="w-[min(38rem,100vw)] overflow-y-auto focus:outline-none sm:!max-w-[38rem]" @open-auto-focus="focusDrawer">
        <template v-if="selected">
          <SheetHeader class="gap-2 border-b border-line-subtle pr-12 pb-3">
            <div class="flex flex-wrap items-center gap-1.5">
              <span class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 font-mono text-[0.6875rem] leading-none font-medium whitespace-nowrap tabular-nums" :class="severityTone(selected.severity)">
                <span class="size-1.5 rounded-full" :class="severityDot(selected.severity)" aria-hidden="true" />
                {{ selected.severity }}
              </span>
              <span class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-[0.6875rem] leading-none font-medium" :class="stateConfig[selected.state].tone">
                <component :is="stateConfig[selected.state].icon" :size="11" :stroke-width="2" aria-hidden="true" />
                {{ INCIDENT_STATE_LABELS[selected.state] }}
              </span>
              <GovernCopyId :id="selected.id" label="Incident ID" />
            </div>
            <SheetTitle class="text-lg leading-6 text-pretty">{{ selected.title }}</SheetTitle>
            <SheetDescription class="flex flex-wrap items-center gap-x-1.5 text-xs leading-4 text-fg-3">
              <span>{{ selected.service }}</span>
              <span aria-hidden="true">·</span>
              <span>{{ selected.env }}</span>
              <span aria-hidden="true">·</span>
              <span>opened {{ formatGovernRelative(selected.startedAt) }}</span>
            </SheetDescription>
          </SheetHeader>

          <div class="mt-4 space-y-4">
            <section class="rounded-lg border border-line-subtle bg-surface px-4 py-3">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p class="text-[0.6875rem] text-fg-3">Impact</p>
                  <p class="mt-0.5 text-sm font-medium" :class="selected.impact === 'none' ? 'text-fg-2' : selected.impact === 'partial' ? 'text-crit' : 'text-warn'">
                    {{ selected.impactSummary }}
                  </p>
                </div>
                <p class="font-mono text-xs text-fg-3" :title="formatGovernStamp(selected.updatedAt)">
                  updated {{ formatGovernRelative(selected.updatedAt) }}
                </p>
              </div>
              <dl class="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 border-t border-line-subtle pt-3 text-xs sm:grid-cols-3">
                <div>
                  <dt class="text-fg-3">Owner</dt>
                  <dd class="mt-0.5 text-fg-1">{{ selected.owner ?? "Unassigned" }}</dd>
                </div>
                <div>
                  <dt class="text-fg-3">Sessions</dt>
                  <dd class="mt-0.5 font-mono text-fg-1 tabular-nums">{{ selected.affectedSessions ?? "—" }}</dd>
                </div>
                <div>
                  <dt class="text-fg-3">Runs</dt>
                  <dd class="mt-0.5 font-mono text-fg-1 tabular-nums">{{ selected.affectedRuns ?? "—" }}</dd>
                </div>
              </dl>
            </section>

            <section>
              <h3 class="text-xs font-semibold text-fg-1">Timestamps</h3>
              <dl class="mt-2 divide-y divide-line-subtle overflow-hidden rounded-lg border border-line-subtle bg-surface text-xs">
                <div v-for="row in [
                  { label: 'Started', value: selected.startedAt },
                  { label: 'Detected', value: selected.detectedAt },
                  { label: 'Acknowledged', value: selected.acknowledgedAt },
                  { label: 'Mitigated', value: selected.mitigatedAt },
                  { label: 'Resolved', value: selected.resolvedAt },
                ]" :key="row.label" class="flex items-center justify-between gap-3 px-4 py-2">
                  <dt class="text-fg-3">{{ row.label }}</dt>
                  <dd class="font-mono text-fg-2" :class="!row.value && 'text-fg-off'">{{ row.value ? formatGovernStamp(row.value) : "—" }}</dd>
                </div>
              </dl>
            </section>

            <section>
              <h3 class="text-xs font-semibold text-fg-1">Response timeline</h3>
              <ol class="mt-2 divide-y divide-line-subtle overflow-hidden rounded-lg border border-line-subtle bg-surface">
                <li v-for="event in selected.timeline" :key="`${event.at}-${event.action}`" class="flex gap-3 px-4 py-2.5">
                  <span class="mt-1.5 size-1.5 shrink-0 rounded-full bg-line-strong" aria-hidden="true" />
                  <div class="min-w-0 flex-1">
                    <div class="flex flex-wrap items-baseline justify-between gap-x-2">
                      <p class="text-xs font-medium text-fg-1">{{ event.action }}</p>
                      <p class="font-mono text-[0.625rem] text-fg-3">{{ formatGovernStamp(event.at) }}</p>
                    </div>
                    <p v-if="event.detail" class="mt-0.5 text-xs leading-5 text-fg-3">{{ event.detail }}</p>
                    <p class="mt-0.5 text-[0.6875rem] text-fg-3">{{ event.actor }}</p>
                  </div>
                </li>
              </ol>
            </section>

            <section v-if="selected.responders.length">
              <h3 class="text-xs font-semibold text-fg-1">Responders</h3>
              <ul class="mt-2 divide-y divide-line-subtle overflow-hidden rounded-lg border border-line-subtle bg-surface">
                <li v-for="responder in selected.responders" :key="responder.name" class="flex items-center justify-between gap-3 px-4 py-2 text-xs">
                  <span class="text-fg-2">{{ responder.name }}</span>
                  <span class="font-mono text-[0.6875rem] text-fg-3">{{ responder.role }}</span>
                </li>
              </ul>
            </section>

            <section v-if="selected.related.length">
              <h3 class="text-xs font-semibold text-fg-1">Related evidence</h3>
              <ul class="mt-2 divide-y divide-line-subtle overflow-hidden rounded-lg border border-line-subtle bg-surface">
                <li v-for="item in selected.related" :key="item.label" class="flex items-center justify-between gap-3 px-4 py-2.5">
                  <div class="min-w-0">
                    <p class="text-xs font-medium text-fg-1">{{ item.label }}</p>
                    <p class="mt-0.5 text-[0.6875rem] text-fg-3">{{ item.detail }}</p>
                  </div>
                  <NuxtLink :to="item.href" class="ix-link shrink-0 text-[0.6875rem]">Open</NuxtLink>
                </li>
              </ul>
            </section>

            <section class="rounded-lg border border-line-subtle bg-surface-2 px-4 py-3">
              <p class="text-xs font-medium text-fg-1">Actions stay visible</p>
              <p class="mt-0.5 text-[0.6875rem] leading-4 text-fg-3">
                Acknowledge, escalate, and resolve need the incident write contract. This console never hides where an action will live.
              </p>
              <div class="mt-2 flex flex-wrap gap-1.5">
                <GovernLockedAction label="Acknowledge" :icon="Eye" size="sm" />
                <GovernLockedAction label="Escalate" :icon="Siren" size="sm" />
                <GovernLockedAction label="Resolve" :icon="CircleDot" size="sm" />
              </div>
            </section>
          </div>
        </template>
      </SheetContent>
    </Sheet>

    <GovernShortcutsDialog v-model:open="shortcutsOpen" :groups="shortcutGroups" />
  </div>
</template>
