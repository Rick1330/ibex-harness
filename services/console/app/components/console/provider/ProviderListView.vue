<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import type { Component } from "vue"
import {
  ArrowDown,
  ArrowUp,
  Check,
  ChevronRight,
  CircleAlert,
  CircleDot,
  KeyRound,
  Plus,
  Search,
  Server,
  ShieldCheck,
  TriangleAlert,
  X,
} from "@lucide/vue"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import AgentMultiFilter from "@/components/console/agent/list/primitives/AgentMultiFilter.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import BrandIcon from "@/components/console/BrandIcon.vue"
import GovernShortcutsDialog from "@/components/console/govern/primitives/GovernShortcutsDialog.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import GovernTabBar from "@/components/console/govern/primitives/GovernTabBar.vue"
import KeyHint from "@/components/console/primitives/KeyHint.vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import { formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"
import {
  CREDENTIAL_STATE_LABELS,
  PROVIDER_CAPABILITY_KEYS,
  PROVIDER_DEFAULT_SORT_DIRECTION,
  PROVIDER_HEALTHS,
  PROVIDER_HEALTH_LABELS,
  PROVIDER_ROLE_LABELS,
  PROVIDER_SORT_LABELS,
  PROVIDER_TABS,
  credentialMatches,
  formatContextWindow,
  formatProviderDue,
  modelMatches,
  modelsForProvider,
  providerById,
  providerHref,
  providerMatches,
  providerModels,
  providerRegions,
  providerSummary,
  providers,
  sortProviders,
  type CredentialState,
  type Provider,
  type ProviderHealth,
  type ProviderListState,
  type ProviderSortKey,
  type ProviderTab,
} from "@/lib/provider-preview"

const props = defineProps<{ state: ProviderListState }>()
const emit = defineEmits<{ update: [state: ProviderListState] }>()

function update(patch: Partial<ProviderListState>): void {
  emit("update", { ...props.state, ...patch })
}

const summary = providerSummary()

// ---- filtering -----------------------------------------------------------
const filteredProviders = computed(() =>
  sortProviders(providers.filter((provider) => providerMatches(provider, props.state)), props.state.sort, props.state.direction),
)
const filteredModels = computed(() =>
  providerModels
    .filter((model) => modelMatches(model, props.state))
    .sort((left, right) => left.provider.localeCompare(right.provider) || left.label.localeCompare(right.label)),
)
const filteredCredentials = computed(() =>
  providers.filter((provider) => credentialMatches(provider, props.state)).sort((left, right) => Date.parse(left.credential.dueAt) - Date.parse(right.credential.dueAt)),
)

const tabCounts = computed<Record<string, string>>(() => ({
  providers: String(providers.length),
  models: String(providerModels.length),
  credentials: String(providers.length),
}))

const healthOptions = computed(() =>
  PROVIDER_HEALTHS.map((health) => ({
    value: health,
    label: PROVIDER_HEALTH_LABELS[health],
    count: providers.filter((provider) => provider.health === health).length,
  })),
)
const regionOptions = computed(() =>
  providerRegions().map((region) => ({
    value: region,
    label: region,
    count: providers.filter((provider) => provider.region === region).length,
  })),
)

const activeFilterCount = computed(
  () => props.state.healths.length + props.state.regions.length + (props.state.search ? 1 : 0),
)

const resultCount = computed(() => {
  if (props.state.tab === "models") return filteredModels.value.length
  if (props.state.tab === "credentials") return filteredCredentials.value.length
  return filteredProviders.value.length
})

const totalCount = computed(() => {
  if (props.state.tab === "models") return providerModels.length
  return providers.length
})

function clearFilters(): void {
  update({ search: "", healths: [], regions: [] })
}

function setTab(tab: ProviderTab): void {
  update({ tab, provider: "" })
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
function toggleSort(key: ProviderSortKey): void {
  if (props.state.sort === key) {
    update({ direction: props.state.direction === "asc" ? "desc" : "asc" })
  } else {
    update({ sort: key, direction: PROVIDER_DEFAULT_SORT_DIRECTION[key] })
  }
}

function ariaSort(key: ProviderSortKey): "ascending" | "descending" | "none" {
  if (props.state.sort !== key) return "none"
  return props.state.direction === "asc" ? "ascending" : "descending"
}

function sortIcon(key: ProviderSortKey) {
  if (props.state.sort !== key) return ArrowUp
  return props.state.direction === "asc" ? ArrowUp : ArrowDown
}

// ---- presentation --------------------------------------------------------
const healthConfig: Record<ProviderHealth, { icon: Component; tone: string }> = {
  healthy: { icon: Check, tone: "border-transparent bg-transparent text-ok" },
  degraded: { icon: TriangleAlert, tone: "border-warn/35 bg-warn-tint text-warn" },
  down: { icon: X, tone: "border-transparent bg-transparent text-crit" },
}

const credentialConfig: Record<CredentialState, { icon: Component; tone: string }> = {
  ok: { icon: CircleDot, tone: "border-line bg-raised text-fg-2" },
  due: { icon: TriangleAlert, tone: "border-warn/35 bg-warn-tint text-warn" },
  overdue: { icon: CircleAlert, tone: "border-transparent bg-transparent text-crit" },
  revoked: { icon: X, tone: "border-line-subtle bg-transparent text-fg-3" },
}

function providerFor(id: string): Provider {
  return providerById(id) ?? providers[0]!
}

function healthEdge(provider: Provider): "critical" | "warning" | undefined {
  if (provider.health === "down") return "critical"
  if (provider.health === "degraded" || provider.credential.state === "overdue") return "warning"
  return undefined
}

// ---- detail drawer -------------------------------------------------------
const selected = computed(() => (props.state.provider ? providerById(props.state.provider) : null))
const detailOpen = computed(() => Boolean(selected.value))
const selectedModels = computed(() => (selected.value ? modelsForProvider(selected.value.id) : []))

function openProvider(provider: Provider, event?: MouseEvent): void {
  if (event && (event.metaKey || event.ctrlKey || event.shiftKey)) {
    window.open(providerHref(props.state, provider.id), "_blank", "noopener")
    return
  }
  update({ provider: provider.id })
}

function closeDetail(open: boolean): void {
  if (!open) update({ provider: "" })
}

function focusDrawer(event: Event): void {
  event.preventDefault()
  void nextTick(() => document.querySelector<HTMLElement>('[data-slot="sheet-content"]')?.focus())
}

function onRowKeydown(event: KeyboardEvent, provider: Provider): void {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault()
    openProvider(provider)
  }
}

// ---- keyboard ------------------------------------------------------------
const shortcutsOpen = ref(false)

function stepTab(delta: number): void {
  const index = PROVIDER_TABS.findIndex((tab) => tab.id === props.state.tab)
  const next = PROVIDER_TABS[(index + delta + PROVIDER_TABS.length) % PROVIDER_TABS.length]
  if (next) setTab(next.id)
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
  } else if (event.key === "[") {
    event.preventDefault()
    stepTab(-1)
  } else if (event.key === "]") {
    event.preventDefault()
    stepTab(1)
  } else if (event.key === "?") {
    event.preventDefault()
    shortcutsOpen.value = true
  } else if (event.key === "Escape") {
    if (selected.value) update({ provider: "" })
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
      { keys: "[ / ]", label: "Previous / next tab" },
      { keys: "?", label: "Show this sheet" },
      { keys: "Esc", label: "Close the drawer or clear search" },
    ],
  },
  {
    title: "This page",
    rows: [
      { keys: "Enter", label: "Open the focused provider" },
      { keys: "Space", label: "Open the focused provider" },
    ],
  },
]

const tiles = [
  {
    label: "Configured",
    value: String(summary.configured),
    helper: `${summary.models} models mapped`,
    tone: "default" as const,
  },
  {
    label: "Healthy",
    value: String(summary.healthy),
    helper: "Declared and observed",
    tone: "success" as const,
  },
  {
    label: "Degraded",
    value: String(summary.degraded),
    helper: summary.degraded ? "Routing confidence is reduced" : "No provider is degraded",
    tone: summary.degraded ? ("warning" as const) : ("default" as const),
  },
  {
    label: "Rotation due",
    value: String(summary.rotationDue),
    helper: summary.rotationDue ? "1 overdue · 1 due within 2d" : "Every credential is current",
    tone: summary.rotationDue ? ("warning" as const) : ("default" as const),
  },
]

const aboutNotes = [
  {
    lead: "A manifest is a claim.",
    body: "Each provider row comes from a manifest. Health and capabilities marked \"declared\" are claims by that manifest; \"verified\" means observed traffic confirmed them.",
  },
  {
    lead: "Degraded is not disabled.",
    body: "A degraded provider keeps its models but loses routing weight. Removing it from the fallback chain is a separate, write-gated action.",
  },
  {
    lead: "Secrets never render.",
    body: "Only a credential prefix, scope, and rotation dates are shown. The console never requests or displays secret material.",
  },
]
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">
    <ConsolePageHeader
      title="Providers"
      definition="Which model providers and credentials this organization can call, and what each one can do."
      :verdict="`Preview renders ${providers.length} illustrative provider manifests and ${providerModels.length} models. The provider registry is not connected, so no live endpoint, model, or credential state is claimed.`"
      contract="operator.providers.v1 [NEEDS-BACKEND]"
      scope="org_demo_42 · all environments"
      range="Current manifests · fixture clock"
      coverage="0% live · illustrative only"
      :notes="aboutNotes"
    >
      <template #actions>
        <GovernLockedAction label="Add provider" :icon="Plus" variant="primary" />
      </template>
    </ConsolePageHeader>

    <section class="grid grid-cols-2 gap-3 xl:grid-cols-4" aria-label="Provider summary">
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
      <div class="px-3 pt-1">
        <GovernTabBar :tabs="PROVIDER_TABS" :model-value="state.tab" :badges="tabCounts" aria-label="Provider views" @update:model-value="setTab($event as ProviderTab)" />
      </div>

      <div class="flex flex-wrap items-center gap-2 border-b border-line-subtle px-3 py-2">
        <div class="relative w-full min-w-0 sm:w-64">
          <Search :size="13" :stroke-width="1.9" class="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-fg-3" aria-hidden="true" />
          <input
            ref="searchInput"
            :value="searchDraft"
            type="search"
            :placeholder="state.tab === 'models' ? 'Search model or provider' : state.tab === 'credentials' ? 'Search prefix, scope, state' : 'Search name, endpoint, region'"
            aria-label="Search providers"
            class="ix-input h-8 pr-9 pl-8 text-xs"
            @input="onSearchInput(($event.target as HTMLInputElement).value)"
            @keydown.enter.prevent="update({ search: searchDraft })"
          >
          <span class="pointer-events-none absolute inset-y-0 right-0.5 flex items-center"><KeyHint>/</KeyHint></span>
        </div>

        <template v-if="state.tab === 'providers'">
          <AgentMultiFilter
            label="Health"
            :options="healthOptions"
            :model-value="state.healths"
            @update:model-value="update({ healths: $event as ProviderHealth[] })"
          />
          <AgentMultiFilter label="Region" :options="regionOptions" :model-value="state.regions" @update:model-value="update({ regions: $event })" />
          <GovernFilterSelect
            label="Sort"
            :model-value="state.sort"
            :options="Object.entries(PROVIDER_SORT_LABELS).map(([value, label]) => ({ value, label }))"
            @update:model-value="update({ sort: $event as ProviderSortKey, direction: PROVIDER_DEFAULT_SORT_DIRECTION[$event as ProviderSortKey] })"
          />
        </template>

        <div class="ml-auto flex items-center gap-2 text-[0.6875rem] leading-4 text-fg-3">
          <span class="font-mono tabular-nums">{{ resultCount }} of {{ totalCount }}</span>
          <button
            v-if="activeFilterCount"
            type="button"
            class="rounded px-1 text-xs font-medium text-fg-2 underline decoration-line-strong underline-offset-3 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            @click="clearFilters"
          >Clear filters</button>
        </div>
      </div>

      <!-- Providers -->
      <div v-if="state.tab === 'providers'" class="overflow-x-auto">
        <table class="ix-list-table min-w-[52rem]" aria-label="Providers">
          <thead>
            <tr>
              <th scope="col" class="w-52" :aria-sort="ariaSort('name')">
                <button type="button" class="ix-sort-button" @click="toggleSort('name')">
                  Provider
                  <component :is="sortIcon('name')" :size="10" :stroke-width="2" :class="state.sort === 'name' ? 'text-fg-2' : 'text-fg-off'" aria-hidden="true" />
                </button>
              </th>
              <th scope="col" class="hidden lg:table-cell">Endpoint</th>
              <th scope="col" class="hidden w-24 xl:table-cell">Auth</th>
              <th scope="col" class="hidden w-24 text-right md:table-cell" :aria-sort="ariaSort('models')">
                <button type="button" class="ix-sort-button ml-auto flex-row-reverse" @click="toggleSort('models')">
                  Models
                  <component :is="sortIcon('models')" :size="10" :stroke-width="2" :class="state.sort === 'models' ? 'text-fg-2' : 'text-fg-off'" aria-hidden="true" />
                </button>
              </th>
              <th scope="col" class="w-32" :aria-sort="ariaSort('health')">
                <button type="button" class="ix-sort-button" @click="toggleSort('health')">
                  Health
                  <component :is="sortIcon('health')" :size="10" :stroke-width="2" :class="state.sort === 'health' ? 'text-fg-2' : 'text-fg-off'" aria-hidden="true" />
                </button>
              </th>
              <th scope="col" class="w-36" :aria-sort="ariaSort('rotation')">
                <button type="button" class="ix-sort-button" @click="toggleSort('rotation')">
                  Rotation
                  <component :is="sortIcon('rotation')" :size="10" :stroke-width="2" :class="state.sort === 'rotation' ? 'text-fg-2' : 'text-fg-off'" aria-hidden="true" />
                </button>
              </th>
              <th scope="col" class="hidden w-28 sm:table-cell">Routing</th>
              <th scope="col" class="w-10"><span class="sr-only">Open</span></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="provider in filteredProviders"
              :key="provider.id"
              :data-provider-row="provider.id"
              :data-edge="healthEdge(provider)"
              :data-selected="state.provider === provider.id"
              tabindex="0"
              :aria-label="`Open ${provider.name}`"
              @click="openProvider(provider, $event)"
              @keydown="onRowKeydown($event, provider)"
            >
              <td>
                <div class="min-w-0">
                  <p class="flex items-center gap-2 truncate text-[0.8125rem] leading-5 font-medium text-fg-1">
                    <BrandIcon :id="provider.id" :size="16" :label="`${provider.name} logo`" />
                    {{ provider.name }}
                  </p>
                  <p class="mt-0.5 truncate font-mono text-[0.6875rem] leading-4 text-fg-3">{{ provider.region }} · {{ provider.id }}</p>
                </div>
              </td>
              <td class="hidden lg:table-cell">
                <span class="block max-w-[22rem] truncate font-mono text-[0.6875rem] text-fg-2" :title="provider.endpoint">{{ provider.endpoint }}</span>
              </td>
              <td class="hidden xl:table-cell">
                <span class="font-mono text-[0.6875rem] text-fg-2">{{ provider.auth }}</span>
              </td>
              <td class="hidden text-right font-mono text-xs text-fg-2 tabular-nums md:table-cell">{{ modelsForProvider(provider.id).length }}</td>
              <td>
                <span class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-[0.6875rem] leading-none font-medium whitespace-nowrap" :class="healthConfig[provider.health].tone">
                  <component :is="healthConfig[provider.health].icon" :size="11" :stroke-width="2.2" aria-hidden="true" />
                  {{ PROVIDER_HEALTH_LABELS[provider.health] }}
                </span>
              </td>
              <td>
                <span class="inline-flex items-center gap-1.5 text-xs" :class="provider.credential.state === 'overdue' ? 'text-crit' : provider.credential.state === 'due' ? 'text-warn' : 'text-fg-2'">
                  <KeyRound :size="12" :stroke-width="1.8" class="shrink-0" aria-hidden="true" />
                  {{ formatProviderDue(provider.credential.dueAt) }}
                </span>
              </td>
              <td class="hidden sm:table-cell">
                <span class="text-xs text-fg-2">{{ PROVIDER_ROLE_LABELS[provider.role] }}</span>
                <span class="ml-1 font-mono text-[0.625rem] text-fg-3 tabular-nums">{{ provider.weightPct }}%</span>
              </td>
              <td>
                <ChevronRight :size="14" :stroke-width="1.8" class="text-fg-off" aria-hidden="true" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Models -->
      <div v-else-if="state.tab === 'models'" class="overflow-x-auto">
        <table class="ix-list-table min-w-[50rem]" aria-label="Models">
          <thead>
            <tr>
              <th scope="col" class="w-56">Model</th>
              <th scope="col" class="w-40">Provider</th>
              <th scope="col" class="w-24 text-right">Context</th>
              <th v-for="capability in PROVIDER_CAPABILITY_KEYS" :key="capability.key" scope="col" class="w-24">{{ capability.label }}</th>
              <th scope="col" class="w-28">Source</th>
              <th scope="col" class="w-10"><span class="sr-only">Open</span></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="model in filteredModels"
              :key="model.id"
              :data-model-row="model.id"
              :data-selected="state.provider === model.providerId"
              tabindex="0"
              :aria-label="`Open ${model.provider} provider details`"
              @click="openProvider(providerFor(model.providerId), $event)"
              @keydown="onRowKeydown($event, providerFor(model.providerId))"
            >
              <td>
                <p class="flex items-center gap-2 truncate text-[0.8125rem] leading-5 font-medium text-fg-1">
                  <BrandIcon :id="model.id" :size="16" :label="`${model.label} logo`" />
                  {{ model.label }}
                </p>
                <p class="mt-0.5 truncate font-mono text-[0.6875rem] leading-4 text-fg-3">{{ model.id }}</p>
              </td>
              <td class="text-xs text-fg-2">{{ model.provider }}</td>
              <td class="text-right font-mono text-xs text-fg-2 tabular-nums">{{ formatContextWindow(model.contextWindow) }}</td>
              <td v-for="capability in PROVIDER_CAPABILITY_KEYS" :key="capability.key">
                <span v-if="model.caps[capability.key]" class="inline-flex items-center gap-1 text-ok">
                  <Check :size="13" :stroke-width="2.2" aria-hidden="true" />
                  <span class="sr-only">Supported</span>
                </span>
                <span v-else class="inline-flex items-center gap-1 text-fg-3">
                  <X :size="13" :stroke-width="2.2" aria-hidden="true" />
                  <span class="sr-only">Not supported</span>
                </span>
              </td>
              <td>
                <span
                  class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-[0.6875rem] leading-none font-medium"
                  :class="model.source === 'verified' ? 'border-transparent bg-transparent text-ok' : 'border-transparent bg-transparent text-warn'"
                >
                  <ShieldCheck v-if="model.source === 'verified'" :size="11" :stroke-width="2" aria-hidden="true" />
                  <CircleAlert v-else :size="11" :stroke-width="2" aria-hidden="true" />
                  {{ model.source === "verified" ? "Verified" : "Declared" }}
                </span>
              </td>
              <td>
                <ChevronRight :size="14" :stroke-width="1.8" class="text-fg-off" aria-hidden="true" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Credentials -->
      <div v-else>
        <div class="overflow-x-auto">
          <table class="ix-list-table min-w-[48rem]" aria-label="Credentials">
            <thead>
              <tr>
                <th scope="col" class="w-52">Provider</th>
                <th scope="col" class="w-44">Prefix</th>
                <th scope="col" class="hidden w-28 sm:table-cell">Scope</th>
                <th scope="col" class="hidden w-40 md:table-cell">Rotated</th>
                <th scope="col" class="w-32">Next due</th>
                <th scope="col" class="w-28">State</th>
                <th scope="col" class="w-10"><span class="sr-only">Open</span></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="provider in filteredCredentials"
                :key="provider.id"
                :data-credential-row="provider.id"
                :data-edge="provider.credential.state === 'overdue' ? 'warning' : undefined"
                tabindex="0"
                :aria-label="`Open ${provider.name} credential details`"
                @click="openProvider(provider, $event)"
                @keydown="onRowKeydown($event, provider)"
              >
                <td class="text-xs font-medium text-fg-1">
                  <span class="inline-flex items-center gap-2"><BrandIcon :id="provider.id" :size="14" :label="`${provider.name} logo`" />{{ provider.name }}</span>
                </td>
                <td class="font-mono text-[0.6875rem] text-fg-2">{{ provider.credential.prefix }}</td>
                <td class="hidden font-mono text-[0.6875rem] text-fg-3 sm:table-cell">{{ provider.credential.scope }}</td>
                <td class="hidden md:table-cell">
                  <span class="font-mono text-xs text-fg-2" :title="formatGovernStamp(provider.credential.rotatedAt)">{{ formatGovernRelative(provider.credential.rotatedAt) }}</span>
                </td>
                <td>
                  <span class="text-xs" :class="provider.credential.state === 'overdue' ? 'text-crit' : provider.credential.state === 'due' ? 'text-warn' : 'text-fg-2'">
                    {{ formatProviderDue(provider.credential.dueAt) }}
                  </span>
                </td>
                <td>
                  <span class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-[0.6875rem] leading-none font-medium whitespace-nowrap" :class="credentialConfig[provider.credential.state].tone">
                    <component :is="credentialConfig[provider.credential.state].icon" :size="11" :stroke-width="2" aria-hidden="true" />
                    {{ CREDENTIAL_STATE_LABELS[provider.credential.state] }}
                  </span>
                </td>
                <td>
                  <ChevronRight :size="14" :stroke-width="1.8" class="text-fg-off" aria-hidden="true" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="grid gap-x-6 gap-y-2 border-t border-line-subtle bg-surface-2/40 px-4 py-3 sm:grid-cols-2 xl:grid-cols-3">
          <div v-for="row in [
            { label: 'Rotation window', value: '30 days' },
            { label: 'Overlap window', value: '24 hours' },
            { label: 'Revoke after propagation', value: '10 minutes' },
            { label: 'Step-up requirement', value: 'Admin + MFA' },
            { label: 'Sweep cadence', value: 'Every 15 minutes' },
            { label: 'Audit action', value: 'credential.rotate' },
          ]" :key="row.label" class="flex items-baseline justify-between gap-3 text-xs">
            <span class="text-fg-3">{{ row.label }}</span>
            <span class="font-mono text-fg-2">{{ row.value }}</span>
          </div>
        </div>
      </div>

      <GovernEmptyState
        v-if="!resultCount"
        title="Nothing matches this view"
        reason="Clear the search or filters, or switch to another provider tab."
        action-label="Clear filters"
        class="m-3"
        @action="clearFilters"
      />

      <div class="flex flex-wrap items-center justify-between gap-2 border-t border-line-subtle px-4 py-2 text-[0.6875rem] leading-4 text-fg-3">
        <span>Secrets are never rendered. Only prefixes, scopes, and rotation dates appear.</span>
        <span class="font-mono">Read-only · provider writes need a contract</span>
      </div>
    </section>

    <Sheet :open="detailOpen" @update:open="closeDetail">
      <SheetContent side="right" tabindex="-1" class="w-[min(36rem,100vw)] overflow-y-auto focus:outline-none sm:!max-w-[36rem]" @open-auto-focus="focusDrawer">
        <template v-if="selected">
          <SheetHeader class="gap-2 border-b border-line-subtle pr-12 pb-3">
            <div class="flex flex-wrap items-center gap-1.5">
              <span class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-[0.6875rem] leading-none font-medium" :class="healthConfig[selected.health].tone">
                <component :is="healthConfig[selected.health].icon" :size="11" :stroke-width="2.2" aria-hidden="true" />
                {{ PROVIDER_HEALTH_LABELS[selected.health] }}
              </span>
              <span class="inline-flex h-5.5 items-center rounded-full border border-line bg-raised px-2 text-[0.6875rem] leading-none font-medium text-fg-2">
                {{ PROVIDER_ROLE_LABELS[selected.role] }} · {{ selected.weightPct }}%
              </span>
              <GovernCopyId :id="selected.id" label="Provider ID" />
            </div>
            <SheetTitle class="text-lg leading-6 text-pretty">{{ selected.name }}</SheetTitle>
            <SheetDescription class="text-xs leading-4 text-fg-3">
              {{ selected.region }} · {{ selected.auth }} · {{ selected.endpoint }}
            </SheetDescription>
          </SheetHeader>

          <div class="mt-4 space-y-4">
            <section v-if="selected.healthNote" class="rounded-lg border border-warn/30 bg-warn-tint px-4 py-3 text-xs leading-5 text-warn">
              <p class="flex items-start gap-2">
                <TriangleAlert :size="13" :stroke-width="1.9" class="mt-0.5 shrink-0" aria-hidden="true" />
                {{ selected.healthNote }}
              </p>
            </section>

            <section class="rounded-lg border border-line-subtle bg-surface px-4 py-3">
              <h3 class="text-xs font-semibold text-fg-1">Routing</h3>
              <dl class="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                <div>
                  <dt class="text-fg-3">Role</dt>
                  <dd class="mt-0.5 text-fg-1">{{ PROVIDER_ROLE_LABELS[selected.role] }}</dd>
                </div>
                <div>
                  <dt class="text-fg-3">Weight</dt>
                  <dd class="mt-0.5 font-mono text-fg-1 tabular-nums">{{ selected.weightPct }}%</dd>
                </div>
                <div>
                  <dt class="text-fg-3">Falls back to</dt>
                  <dd class="mt-0.5 text-fg-1">{{ selected.fallback ? providerById(selected.fallback)?.name ?? selected.fallback : "—" }}</dd>
                </div>
                <div>
                  <dt class="text-fg-3">Limits</dt>
                  <dd class="mt-0.5 font-mono text-fg-1">{{ selected.limits.rpm.toLocaleString("en-GB") }} rpm · {{ selected.limits.streams }} streams</dd>
                </div>
              </dl>
            </section>

            <section>
              <h3 class="text-xs font-semibold text-fg-1">Models on this provider</h3>
              <ul class="mt-2 divide-y divide-line-subtle overflow-hidden rounded-lg border border-line-subtle bg-surface">
                <li v-for="model in selectedModels" :key="model.id" class="flex items-center justify-between gap-3 px-4 py-2.5">
                  <div class="min-w-0">
                    <p class="truncate font-mono text-xs text-fg-1">{{ model.label }}</p>
                    <p class="mt-0.5 font-mono text-[0.625rem] text-fg-3">{{ formatContextWindow(model.contextWindow) }} context</p>
                  </div>
                  <span
                    class="inline-flex h-5 items-center gap-1 rounded-full border px-1.5 text-[0.625rem] font-medium"
                    :class="model.source === 'verified' ? 'border-transparent bg-transparent text-ok' : 'border-transparent bg-transparent text-warn'"
                  >{{ model.source === "verified" ? "Verified" : "Declared" }}</span>
                </li>
                <li v-if="!selectedModels.length" class="px-4 py-3 text-xs text-fg-3">No model is mapped to this provider.</li>
              </ul>
            </section>

            <section class="rounded-lg border border-line-subtle bg-surface px-4 py-3">
              <h3 class="flex items-center gap-1.5 text-xs font-semibold text-fg-1">
                <KeyRound :size="12" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
                Credential
              </h3>
              <dl class="mt-2 space-y-1.5 text-xs">
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-fg-3">Prefix</dt>
                  <dd class="font-mono text-fg-1">{{ selected.credential.prefix }}</dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-fg-3">Rotated</dt>
                  <dd class="font-mono text-fg-1">{{ formatGovernStamp(selected.credential.rotatedAt) }}</dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-fg-3">Next due</dt>
                  <dd class="text-fg-1">{{ formatGovernStamp(selected.credential.dueAt) }} ({{ formatProviderDue(selected.credential.dueAt) }})</dd>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <dt class="text-fg-3">Rotated by</dt>
                  <dd class="text-fg-1">{{ selected.credential.rotatedBy }}</dd>
                </div>
              </dl>
              <p class="mt-2 border-t border-line-subtle pt-2 text-[0.6875rem] leading-4 text-fg-3">
                Rotation creates an overlap window, then revokes the old secret after propagation. Secret material is never requested by the console.
              </p>
            </section>

            <section class="rounded-lg border border-line-subtle bg-surface-2 px-4 py-3">
              <p class="text-xs font-medium text-fg-1">Actions stay visible</p>
              <p class="mt-0.5 text-[0.6875rem] leading-4 text-fg-3">
                Rotate credential, change routing weight, and disable the provider need the provider write contract.
              </p>
              <div class="mt-2 flex flex-wrap gap-1.5">
                <GovernLockedAction label="Rotate credential" :icon="KeyRound" size="sm" />
                <GovernLockedAction label="Edit routing" :icon="Server" size="sm" />
                <GovernLockedAction label="Disable provider" :icon="X" size="sm" variant="destructive" />
              </div>
            </section>
          </div>
        </template>
      </SheetContent>
    </Sheet>

    <GovernShortcutsDialog v-model:open="shortcutsOpen" :groups="shortcutGroups" />
  </div>
</template>
