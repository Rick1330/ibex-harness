<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import type { Component } from "vue"
import {
  Ban,
  Check,
  ChevronRight,
  CircleAlert,
  Eye,
  Globe2,
  Lock,
  Pencil,
  Search,
  ShieldCheck,
  Terminal,
  UserCheck,
  Wrench,
  X,
} from "@lucide/vue"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import AgentMultiFilter from "@/components/console/agent/list/primitives/AgentMultiFilter.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import GovernHashTag from "@/components/console/govern/primitives/GovernHashTag.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import GovernShortcutsDialog from "@/components/console/govern/primitives/GovernShortcutsDialog.vue"
import GovernTabBar from "@/components/console/govern/primitives/GovernTabBar.vue"
import MemoryKbd from "@/components/console/memory/list/primitives/MemoryKbd.vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import { formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"
import {
  TOOL_APPROVAL_LABELS,
  TOOL_DEFAULT_SORT_DIRECTION,
  TOOL_EFFECTS,
  TOOL_EFFECT_LABELS,
  TOOL_IDEMPOTENCY_LABELS,
  TOOL_PERMISSION_MATRIX,
  TOOL_PERMISSIONS,
  TOOL_ROLES,
  TOOL_SORT_LABELS,
  TOOL_STATUSES,
  TOOL_STATUS_LABELS,
  TOOL_TABS,
  invocationMatches,
  sortTools,
  toolByName,
  toolHref,
  toolInvocations,
  toolMatches,
  toolSchema,
  toolSummary,
  tools,
  type Tool,
  type ToolApproval,
  type ToolEffect,
  type ToolListState,
  type ToolResult,
  type ToolSortKey,
  type ToolStatus,
  type ToolTab,
} from "@/lib/tool-preview"

const props = defineProps<{ state: ToolListState }>()
const emit = defineEmits<{ update: [state: ToolListState] }>()

function update(patch: Partial<ToolListState>): void {
  emit("update", { ...props.state, ...patch })
}

const summary = toolSummary()

// ---- filtering -----------------------------------------------------------
const filteredTools = computed(() =>
  sortTools(tools.filter((tool) => toolMatches(tool, props.state)), props.state.sort, props.state.direction),
)
const filteredInvocations = computed(() => toolInvocations.filter((row) => invocationMatches(row, props.state)))
const resultCount = computed(() => (props.state.tab === "invocations" ? filteredInvocations.value.length : filteredTools.value.length))
const totalCount = computed(() => (props.state.tab === "invocations" ? toolInvocations.length : tools.length))

const effectOptions = computed(() =>
  TOOL_EFFECTS.map((effect) => ({
    value: effect,
    label: TOOL_EFFECT_LABELS[effect],
    count: tools.filter((tool) => tool.effect === effect).length,
  })),
)
const statusOptions = computed(() =>
  TOOL_STATUSES.map((status) => ({
    value: status,
    label: TOOL_STATUS_LABELS[status],
    count: tools.filter((tool) => tool.status === status).length,
  })),
)

const activeFilterCount = computed(
  () => props.state.effects.length + props.state.statuses.length + (props.state.search ? 1 : 0),
)

const tabCounts = computed<Record<string, string>>(() => ({
  tools: String(tools.length),
  invocations: String(toolInvocations.length),
  permissions: String(TOOL_ROLES.length),
}))

function clearFilters(): void {
  update({ search: "", effects: [], statuses: [] })
}

function setTab(tab: ToolTab): void {
  update({ tab, tool: "" })
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



// ---- presentation --------------------------------------------------------
const effectConfig: Record<ToolEffect, { icon: Component; tone: string }> = {
  "read-only": { icon: Eye, tone: "border-line bg-raised text-fg-2" },
  mutating: { icon: Pencil, tone: "border-warn/35 bg-warn-tint text-warn" },
  external: { icon: Globe2, tone: "border-accent/30 bg-accent-tint text-accent" },
}

const approvalConfig: Record<ToolApproval, { icon: Component; tone: string }> = {
  never: { icon: ShieldCheck, tone: "border-line-subtle bg-transparent text-fg-3" },
  "step-up": { icon: UserCheck, tone: "border-warn/35 bg-warn-tint text-warn" },
  policy: { icon: ShieldCheck, tone: "border-line bg-raised text-fg-2" },
}

const resultConfig: Record<ToolResult, { icon: Component; tone: string; label: string }> = {
  ok: { icon: Check, tone: "border-transparent bg-transparent text-ok", label: "Allowed" },
  denied: { icon: Ban, tone: "border-transparent bg-transparent text-crit", label: "Denied" },
  error: { icon: X, tone: "border-transparent bg-transparent text-crit", label: "Failed" },
}

function invocationLatency(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}

// ---- detail drawer -------------------------------------------------------
const selected = computed(() => (props.state.tool ? toolByName(props.state.tool) : null))
const detailOpen = computed(() => Boolean(selected.value))
const selectedSchema = computed(() => (selected.value ? toolSchema(selected.value) : ""))

function openTool(tool: Tool, event?: MouseEvent): void {
  if (event && (event.metaKey || event.ctrlKey || event.shiftKey)) {
    window.open(toolHref(props.state, tool.name), "_blank", "noopener")
    return
  }
  update({ tool: tool.name })
}

function closeDetail(open: boolean): void {
  if (!open) update({ tool: "" })
}

function focusDrawer(event: Event): void {
  event.preventDefault()
  void nextTick(() => document.querySelector<HTMLElement>('[data-slot="sheet-content"]')?.focus())
}


// ---- keyboard ------------------------------------------------------------
const shortcutsOpen = ref(false)

function stepTab(delta: number): void {
  const index = TOOL_TABS.findIndex((tab) => tab.id === props.state.tab)
  const next = TOOL_TABS[(index + delta + TOOL_TABS.length) % TOOL_TABS.length]
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
    if (selected.value) update({ tool: "" })
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
      { keys: "Enter", label: "Open the focused tool" },
      { keys: "Space", label: "Open the focused tool" },
    ],
  },
]


const aboutNotes = [
  {
    lead: "A tool is a capability, not a command.",
    body: "The console lists what an agent may call. Invoking a tool is a separate, permissioned action that requires its own contract and audit record.",
  },
  {
    lead: "Side effect drives the approval.",
    body: "Read-only tools never need a step-up. Mutating tools do. External tools defer to the policy engine because the third party has its own rules.",
  },
  {
    lead: "Schemas are pinned.",
    body: "Each tool row carries the schema version and hash that was approved. A schema change needs re-approval before it can be invoked.",
  },
]

const TOOL_GROUPS: { effect: ToolEffect; label: string; description: string }[] = [
  { effect: "read-only", label: "Read-only", description: "Reads metadata or content and cannot change external state." },
  { effect: "mutating", label: "Mutating", description: "Changes workspace state. Approval and idempotency are part of the contract." },
  { effect: "external", label: "External", description: "Sends data outside the workspace. Policy decides when it may run." },
]

const groupedTools = computed(() =>
  TOOL_GROUPS.map((group) => ({
    ...group,
    tools: filteredTools.value.filter((tool) => tool.effect === group.effect),
  })).filter((group) => group.tools.length > 0),
)
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">
    <ConsolePageHeader
      title="MCP tools"
      definition="Which operator tools exist, what they touch, and who may call them."
      :verdict="`Preview renders ${tools.length} illustrative tools across ${summary.servers} MCP servers. The tool catalogue, schemas, and invocation log are not connected, so no live capability or invocation is claimed.`"
      contract="operator.mcp.tools.v1 [NEEDS-BACKEND]"
      scope="org_demo_42 · workspace connector"
      range="Current catalogue · fixture clock"
      coverage="0% live · illustrative only"
      :notes="aboutNotes"
    >
      <template #actions>
        <GovernLockedAction label="Register server" :icon="Wrench" variant="primary" />
      </template>
      <p class="flex flex-wrap items-center gap-x-4 gap-y-1 text-[0.6875rem] text-fg-3">
        <span>{{ summary.total }} tools across {{ summary.servers }} servers</span>
        <span>{{ summary.readOnly }} read-only</span>
        <span>{{ summary.stateChanging }} state-changing</span>
        <span>{{ summary.stepUp }} require step-up</span>
        <span>{{ summary.disabled }} disabled</span>
      </p>
    </ConsolePageHeader>

    <section class="overflow-hidden rounded-lg border border-line-subtle bg-surface">
      <div class="px-3 pt-1">
        <GovernTabBar :tabs="TOOL_TABS" :model-value="state.tab" :badges="tabCounts" aria-label="Tool views" @update:model-value="setTab($event as ToolTab)" />
      </div>

      <div class="flex flex-wrap items-center gap-2 border-b border-line-subtle px-3 py-2">
        <div class="relative w-full min-w-0 sm:w-64">
          <Search :size="13" :stroke-width="1.9" class="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-fg-3" aria-hidden="true" />
          <input
            ref="searchInput"
            :value="searchDraft"
            type="search"
            :placeholder="state.tab === 'invocations' ? 'Search tool, agent, result' : 'Search tool, server, description'"
            aria-label="Search MCP tools"
            class="ix-input h-8 pr-9 pl-8 text-xs"
            @input="onSearchInput(($event.target as HTMLInputElement).value)"
            @keydown.enter.prevent="update({ search: searchDraft })"
          >
          <span class="pointer-events-none absolute inset-y-0 right-0.5 flex items-center"><MemoryKbd>/</MemoryKbd></span>
        </div>

        <template v-if="state.tab === 'tools'">
          <AgentMultiFilter
            label="Side effect"
            :options="effectOptions"
            :model-value="state.effects"
            @update:model-value="update({ effects: $event as ToolEffect[] })"
          />
          <AgentMultiFilter
            label="Status"
            :options="statusOptions"
            :model-value="state.statuses"
            @update:model-value="update({ statuses: $event as ToolStatus[] })"
          />
          <GovernFilterSelect
            label="Sort"
            :model-value="state.sort"
            :options="Object.entries(TOOL_SORT_LABELS).map(([value, label]) => ({ value, label }))"
            @update:model-value="update({ sort: $event as ToolSortKey, direction: TOOL_DEFAULT_SORT_DIRECTION[$event as ToolSortKey] })"
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

      <!-- Catalogue -->
      <div v-if="state.tab === 'tools'" class="flex flex-col gap-4 p-3">
        <section v-for="group in groupedTools" :key="group.effect" class="flex flex-col gap-2">
          <div class="flex items-baseline justify-between gap-3">
            <div>
              <h2 class="text-[0.625rem] font-medium tracking-[0.12em] text-fg-3 uppercase">{{ group.label }}</h2>
              <p class="mt-0.5 text-[0.6875rem] text-fg-3">{{ group.description }}</p>
            </div>
            <span class="font-mono text-[0.6875rem] text-fg-3 tabular-nums">{{ group.tools.length }}</span>
          </div>
          <div class="overflow-hidden rounded-lg border border-line-subtle bg-surface">
            <button
              v-for="tool in group.tools"
              :key="tool.name"
              type="button"
              :data-tool-row="tool.name"
              :data-selected="state.tool === tool.name"
              :aria-label="`Open ${tool.name}`"
              class="flex w-full items-center gap-3 border-b border-line-subtle px-3 py-2.5 text-left transition-colors last:border-b-0 hover:bg-raised focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-accent"
              @click="openTool(tool)"
            >
              <span
                class="flex size-7 shrink-0 items-center justify-center rounded-md border border-line-subtle bg-canvas text-fg-3"
                aria-hidden="true"
              >
                <component :is="effectConfig[tool.effect].icon" :size="14" :stroke-width="1.8" />
              </span>
              <span class="min-w-0 flex-1">
                <span class="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                  <span class="font-mono text-xs font-medium text-fg-1">{{ tool.name }}</span>
                  <span class="font-mono text-[0.625rem] text-fg-3">v{{ tool.schemaVersion }}</span>
                  <span class="text-[0.625rem] text-fg-3">{{ tool.server }}</span>
                </span>
                <span class="mt-0.5 line-clamp-2 block text-[0.6875rem] leading-4 text-fg-3 sm:truncate">{{ tool.description }}</span>
                <span class="mt-1 hidden flex-wrap items-center gap-x-3 gap-y-0.5 text-[0.625rem] text-fg-3 sm:flex">
                  <span>{{ TOOL_IDEMPOTENCY_LABELS[tool.idempotency] }}</span>
                  <span aria-hidden="true">·</span>
                  <span>{{ TOOL_APPROVAL_LABELS[tool.approval] }}</span>
                  <span aria-hidden="true">·</span>
                  <span class="font-mono">{{ tool.schemaHash.slice(0, 12) }}</span>
                </span>
              </span>
              <span
                class="inline-flex h-4 w-7 shrink-0 items-center rounded-full border px-0.5 transition-colors"
                :class="tool.status === 'enabled' ? 'border-accent/40 bg-accent/20' : 'border-line bg-raised'"
                :aria-label="tool.status === 'enabled' ? 'Enabled, read-only' : 'Disabled'"
                :title="tool.status === 'enabled' ? 'Enabled · read-only console' : 'Disabled · read-only console'"
                role="img"
              >
                <span
                  class="block size-3 rounded-full transition-transform"
                  :class="tool.status === 'enabled' ? 'translate-x-3 bg-accent' : 'translate-x-0 bg-fg-off'"
                />
              </span>
              <ChevronRight :size="14" :stroke-width="1.8" class="shrink-0 text-fg-off" aria-hidden="true" />
            </button>
          </div>
        </section>
        <GovernEmptyState
          v-if="groupedTools.length === 0"
          title="No tools match these filters"
          reason="The search and side-effect filters exclude every tool in the catalogue."
          next-step="Clear the filters to see all tools."
          action-label="Clear filters"
          @action="clearFilters"
        />
      </div>

      <!-- Invocations -->
      <div v-else-if="state.tab === 'invocations'" class="overflow-x-auto">
        <table class="ix-list-table min-w-[46rem]" aria-label="Recent tool invocations">
          <thead>
            <tr>
              <th scope="col" class="w-64">Tool</th>
              <th scope="col" class="w-44">Agent</th>
              <th scope="col" class="w-28">Result</th>
              <th scope="col" class="w-24 text-right">Latency</th>
              <th scope="col" class="w-28 text-right">Time</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in filteredInvocations"
              :key="row.id"
              :data-invocation-row="row.id"
              tabindex="0"
              :aria-label="`Open ${row.tool}`"
              @click="toolByName(row.tool) && openTool(toolByName(row.tool)!)"
              @keydown.enter="toolByName(row.tool) && openTool(toolByName(row.tool)!)"
            >
              <td>
                <div class="min-w-0">
                  <p class="truncate font-mono text-[0.8125rem] leading-5 text-fg-1">{{ row.tool }}</p>
                  <p class="mt-0.5 truncate font-mono text-[0.6875rem] leading-4 text-fg-3">{{ row.id }}</p>
                </div>
              </td>
              <td class="font-mono text-xs text-fg-2">{{ row.actor }}</td>
              <td>
                <span class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-[0.6875rem] leading-none font-medium" :class="resultConfig[row.result].tone">
                  <component :is="resultConfig[row.result].icon" :size="11" :stroke-width="2.2" aria-hidden="true" />
                  {{ resultConfig[row.result].label }}
                </span>
              </td>
              <td class="text-right font-mono text-xs text-fg-2 tabular-nums">{{ invocationLatency(row.latencyMs) }}</td>
              <td class="text-right font-mono text-[0.6875rem] text-fg-3" :title="formatGovernStamp(row.at)">{{ formatGovernRelative(row.at) }}</td>
            </tr>
          </tbody>
        </table>
        <div class="border-t border-line-subtle px-4 py-2 text-[0.6875rem] leading-4 text-fg-3">
          Invocation rows are fixture samples. A denied call is still an audited call; latency is end-to-end tool time, not model time.
        </div>
      </div>

      <!-- Permissions -->
      <div v-else class="overflow-x-auto">
        <table class="ix-list-table min-w-[44rem]" aria-label="Tool permission matrix">
          <thead>
            <tr>
              <th scope="col" class="w-40">Role</th>
              <th v-for="permission in TOOL_PERMISSIONS" :key="permission" scope="col" class="w-32">{{ permission }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="role in TOOL_ROLES" :key="role" data-static="true">
              <td class="text-xs font-medium text-fg-1">{{ role }}</td>
              <td v-for="(allowed, index) in TOOL_PERMISSION_MATRIX[role]" :key="`${role}-${index}`">
                <span v-if="allowed" class="inline-flex items-center gap-1.5 text-xs text-ok">
                  <Check :size="13" :stroke-width="2.2" aria-hidden="true" />
                  Allowed
                </span>
                <span v-else class="inline-flex items-center gap-1.5 text-xs text-fg-3">
                  <Lock :size="12" :stroke-width="1.9" aria-hidden="true" />
                  Not allowed
                </span>
              </td>
            </tr>
          </tbody>
        </table>
        <div class="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line-subtle px-4 py-2 text-[0.6875rem] leading-4 text-fg-3">
          <span class="inline-flex items-center gap-1.5"><Lock :size="12" :stroke-width="1.8" aria-hidden="true" />Mutating tools require step-up</span>
          <span class="inline-flex items-center gap-1.5"><ShieldCheck :size="12" :stroke-width="1.8" aria-hidden="true" />Every invocation is audited</span>
        </div>
      </div>

      <GovernEmptyState
        v-if="!resultCount"
        title="Nothing matches this view"
        reason="Clear the search or filters, or switch to another tab."
        action-label="Clear filters"
        class="m-3"
        @action="clearFilters"
      />

      <div class="flex flex-wrap items-center justify-between gap-2 border-t border-line-subtle px-4 py-2 text-[0.6875rem] leading-4 text-fg-3">
        <span>Tool catalogue is read-only. Invoking a tool is a separate, permissioned action.</span>
        <span class="font-mono">{{ summary.disabled }} disabled · schema pins verified</span>
      </div>
    </section>

    <Sheet :open="detailOpen" @update:open="closeDetail">
      <SheetContent side="right" tabindex="-1" class="w-[min(38rem,100vw)] overflow-y-auto focus:outline-none sm:!max-w-[38rem]" @open-auto-focus="focusDrawer">
        <template v-if="selected">
          <SheetHeader class="gap-2 border-b border-line-subtle pr-12 pb-3">
            <div class="flex flex-wrap items-center gap-1.5">
              <span class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-[0.6875rem] leading-none font-medium" :class="effectConfig[selected.effect].tone">
                <component :is="effectConfig[selected.effect].icon" :size="11" :stroke-width="2" aria-hidden="true" />
                {{ TOOL_EFFECT_LABELS[selected.effect] }}
              </span>
              <span class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-[0.6875rem] leading-none font-medium" :class="approvalConfig[selected.approval].tone">
                <component :is="approvalConfig[selected.approval].icon" :size="11" :stroke-width="2" aria-hidden="true" />
                {{ TOOL_APPROVAL_LABELS[selected.approval] }}
              </span>
              <GovernCopyId :id="selected.name" label="Tool name" />
            </div>
            <SheetTitle class="font-mono text-lg leading-6 text-pretty">{{ selected.name }}</SheetTitle>
            <SheetDescription class="text-xs leading-4 text-fg-3">{{ selected.description }}</SheetDescription>
          </SheetHeader>

          <div class="mt-4 space-y-4">
            <section class="rounded-lg border border-line-subtle bg-surface px-4 py-3">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <h3 class="flex items-center gap-1.5 text-xs font-semibold text-fg-1">
                  <Terminal :size="12" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
                  Input schema
                </h3>
                <GovernHashTag :hash="selected.schemaHash" label="Schema hash" />
              </div>
              <pre class="mt-2 overflow-x-auto rounded-lg border border-line-subtle bg-surface-2 p-3 font-mono text-[0.6875rem] leading-5 text-fg-2" tabindex="0" aria-label="Tool input schema"><code>{{ selectedSchema }}</code></pre>
              <p class="mt-2 text-[0.625rem] text-fg-3">Pinned schema version {{ selected.schemaVersion }}. A change requires re-approval.</p>
            </section>

            <section class="rounded-lg border border-line-subtle bg-surface px-4 py-3">
              <h3 class="text-xs font-semibold text-fg-1">Limits and connection</h3>
              <dl class="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                <div><dt class="text-fg-3">Input bounds</dt><dd class="mt-0.5 font-mono text-fg-1">{{ selected.bounds.input }}</dd></div>
                <div><dt class="text-fg-3">Output shape</dt><dd class="mt-0.5 font-mono text-fg-1">{{ selected.bounds.output }}</dd></div>
                <div><dt class="text-fg-3">Timeout</dt><dd class="mt-0.5 font-mono text-fg-1">{{ selected.bounds.timeout }}</dd></div>
                <div><dt class="text-fg-3">Idempotency key</dt><dd class="mt-0.5 font-mono text-fg-1">{{ selected.bounds.idempotencyKey }}</dd></div>
                <div><dt class="text-fg-3">Transport</dt><dd class="mt-0.5 font-mono text-fg-1">{{ selected.transport }}</dd></div>
                <div><dt class="text-fg-3">Auth</dt><dd class="mt-0.5 font-mono text-fg-1">{{ selected.auth }}</dd></div>
              </dl>
              <p class="mt-2 border-t border-line-subtle pt-2 text-[0.6875rem] leading-4 text-fg-3">
                The server is reached only through the operator BFF. Origin pinning allows 5 minutes of clock skew; credentials never enter the browser.
              </p>
            </section>

            <section>
              <h3 class="text-xs font-semibold text-fg-1">Sample invocations</h3>
              <ul v-if="selected.invocations.length" class="mt-2 divide-y divide-line-subtle overflow-hidden rounded-lg border border-line-subtle bg-surface">
                <li v-for="row in selected.invocations" :key="row.id" class="flex items-center justify-between gap-3 px-4 py-2.5">
                  <div class="min-w-0">
                    <p class="truncate font-mono text-xs text-fg-1">{{ row.actor }}</p>
                    <p class="mt-0.5 font-mono text-[0.625rem] text-fg-3">{{ formatGovernStamp(row.at) }} · {{ invocationLatency(row.latencyMs) }}</p>
                  </div>
                  <span class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-[0.6875rem] leading-none font-medium" :class="resultConfig[row.result].tone">
                    <component :is="resultConfig[row.result].icon" :size="11" :stroke-width="2.2" aria-hidden="true" />
                    {{ resultConfig[row.result].label }}
                  </span>
                </li>
              </ul>
              <p v-else class="mt-2 rounded-lg border border-dashed border-line-subtle px-4 py-3 text-xs text-fg-3">
                No invocation is recorded for this tool in the fixture window.
              </p>
            </section>

            <section class="rounded-lg border border-line-subtle bg-surface-2 px-4 py-3">
              <p class="flex items-center gap-1.5 text-xs font-medium text-fg-1">
                <CircleAlert :size="12" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
                Actions stay visible
              </p>
              <p class="mt-0.5 text-[0.6875rem] leading-4 text-fg-3">
                Invoke, disable, and re-pin the schema need the tool invocation contract. A disabled tool keeps its schema and history.
              </p>
              <div class="mt-2 flex flex-wrap gap-1.5">
                <GovernLockedAction label="Invoke" :icon="Terminal" size="sm" />
                <GovernLockedAction :label="selected.status === 'enabled' ? 'Disable tool' : 'Enable tool'" :icon="Lock" size="sm" />
                <GovernLockedAction label="Re-pin schema" :icon="ShieldCheck" size="sm" />
              </div>
            </section>
          </div>
        </template>
      </SheetContent>
    </Sheet>

    <GovernShortcutsDialog v-model:open="shortcutsOpen" :groups="shortcutGroups" />
  </div>
</template>
