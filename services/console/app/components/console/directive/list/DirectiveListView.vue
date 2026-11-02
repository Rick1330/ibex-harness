<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import {
  ArrowDown,
  ArrowUp,
  Clock,
  RotateCcw,
  Search,
  ShieldAlert,
  X,
} from "@lucide/vue"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import KeyHint from "@/components/console/primitives/KeyHint.vue"
import DirectiveListHeader from "./DirectiveListHeader.vue"
import DirectiveQuickLook from "./DirectiveQuickLook.vue"
import DirectiveResultCard from "./DirectiveResultCard.vue"
import DirectiveResultRow from "./DirectiveResultRow.vue"
import {
  DIRECTIVE_STATE_FILTER_LABELS,
  directiveAgentOptions,
  directiveCandidate,
  directiveListStats,
  directives,
  filterDirectives,
  sortDirectives,
  type Directive,
  type DirectiveSortKey,
  type DirectiveStateFilter,
  type DirectiveTab,
} from "@/lib/directive-preview"
import {
  DIRECTIVE_SORT_KEYS,
  DIRECTIVE_SORT_LABELS,
  DIRECTIVE_STATE_FILTERS,
  type DirectiveListState,
} from "@/lib/govern-query"
import { formatGovernRelative, formatGovernShortDate, formatGovernWait } from "@/lib/govern-format"

const props = defineProps<{
  state: DirectiveListState
  returnTo: string
}>()

const emit = defineEmits<{ update: [state: DirectiveListState] }>()

function update(patch: Partial<DirectiveListState>): void {
  emit("update", { ...props.state, ...patch })
}

const stats = directiveListStats()
const agentOptions = directiveAgentOptions()

const filtered = computed(() =>
  sortDirectives(
    filterDirectives(directives, { search: props.state.q, agent: props.state.agent, state: props.state.state }),
    props.state.sort,
  ),
)

const stateCounts = computed(() =>
  Object.fromEntries(
    DIRECTIVE_STATE_FILTERS.map((filter) => [
      filter,
      filter === "all" ? directives.length : directives.filter((directive) => directive.versions.some((version) => version.state === filter)).length,
    ]),
  ) as Record<DirectiveStateFilter, number>,
)

const liveCount = computed(() => directives.filter((directive) => directive.versions.some((version) => version.state === "live")).length)

const failingHint = computed(() => {
  for (const directive of directives) {
    const candidate = directiveCandidate(directive)
    if (!candidate) continue
    const failed = candidate.checks.find((check) => check.state === "failed")
    if (failed) return `${directive.name} · ${candidate.version} ${failed.name.toLowerCase()}`
  }
  return "No candidate is blocked"
})

const recentPromotionHint = computed(() => {
  const promotions = directives.flatMap((directive) =>
    directive.versions
      .filter((version) => version.liveFrom !== null)
      .map((version) => ({ directive, version })),
  )
  const latest = promotions.sort((left, right) => Date.parse(right.version.liveFrom ?? "") - Date.parse(left.version.liveFrom ?? ""))[0]
  if (!latest) return "No promotions recorded"
  return `${latest.version.version} promoted ${formatGovernRelative(latest.version.liveFrom)}`
})

const recentRollbackHint = computed(() => {
  const rollbacks = directives.flatMap((directive) =>
    directive.events.filter((event) => event.action === "rolled_back").map((event) => ({ directive, event })),
  )
  const latest = rollbacks.sort((left, right) => Date.parse(right.event.at) - Date.parse(left.event.at))[0]
  if (!latest) return "No rollbacks recorded"
  return `${latest.directive.name} · ${latest.event.version} · ${formatGovernShortDate(latest.event.at)}`
})

const activeFilters = computed(
  () => props.state.q.trim() !== "" || props.state.agent !== "all" || props.state.state !== "all" || props.state.sort !== "change",
)

function clearFilters(): void {
  update({ q: "", agent: "all", state: "all", sort: "change" })
}

// ---- search input (150 ms debounce) --------------------------------------
const searchInput = ref<HTMLInputElement | null>(null)
const searchDraft = ref(props.state.q)
let searchTimer: ReturnType<typeof setTimeout> | null = null

watch(
  () => props.state.q,
  (value) => {
    if (value !== searchDraft.value) searchDraft.value = value
  },
)

function onSearchInput(value: string): void {
  searchDraft.value = value
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    if (value !== props.state.q) update({ q: value })
  }, 150)
}

function submitSearch(): void {
  if (searchTimer) clearTimeout(searchTimer)
  if (searchDraft.value !== props.state.q) update({ q: searchDraft.value })
}

// ---- navigation ----------------------------------------------------------
function directiveHref(directive: Directive, tab: DirectiveTab = "overview"): string {
  const params = new URLSearchParams()
  if (tab !== "overview") params.set("tab", tab)
  if (props.returnTo) params.set("return", props.returnTo)
  const query = params.toString()
  return `/directives/${encodeURIComponent(directive.id)}${query ? `?${query}` : ""}`
}

function openDirective(directive: Directive, tab: DirectiveTab = "overview", event?: MouseEvent): void {
  const href = directiveHref(directive, tab)
  if (event && (event.metaKey || event.ctrlKey || event.shiftKey)) {
    window.open(href, "_blank", "noopener")
    return
  }
  void navigateTo(href)
}


// ---- keyboard selection and quick look -----------------------------------
const selectedIndex = ref(-1)
const selectedId = computed(() => filtered.value[selectedIndex.value]?.id ?? null)
const quickLookOpen = ref(false)
const quickLookId = ref<string | null>(null)
const quickLookDirective = computed(() => directives.find((directive) => directive.id === quickLookId.value) ?? null)

function openQuickLook(directive: Directive): void {
  quickLookId.value = directive.id
  quickLookOpen.value = true
}

function closeQuickLook(open: boolean): void {
  quickLookOpen.value = open
}

function moveSelection(delta: number): void {
  if (!filtered.value.length) return
  const start = selectedIndex.value >= 0 ? selectedIndex.value : quickLookDirective.value ? filtered.value.findIndex((entry) => entry.id === quickLookDirective.value?.id) : -1
  const next = (start + delta + filtered.value.length) % filtered.value.length
  selectedIndex.value = next
  const target = filtered.value[next]!
  if (quickLookOpen.value) quickLookId.value = target.id
  void nextTick(() => {
    document.querySelector<HTMLElement>(`[data-directive-row="${target.id}"]`)?.focus()
  })
}

watch(
  () => filtered.value.map((directive) => directive.id).join("|"),
  () => {
    if (selectedIndex.value >= filtered.value.length) selectedIndex.value = filtered.value.length - 1
  },
)

// ---- shortcuts ----------------------------------------------------------
const shortcutsDialog = ref<HTMLDialogElement | null>(null)

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
  } else if (event.key === "?") {
    event.preventDefault()
    shortcutsDialog.value?.showModal()
  } else if (event.key === "Escape") {
    if (quickLookOpen.value) closeQuickLook(false)
    else if (shortcutsDialog.value?.open) shortcutsDialog.value.close()
    else if (searchDraft.value) {
      searchDraft.value = ""
      update({ q: "" })
    }
  } else if (event.key === "Enter" && selectedIndex.value >= 0) {
    const directive = filtered.value[selectedIndex.value]
    if (directive && (event.target === document.body || event.target === document.documentElement)) {
      event.preventDefault()
      openDirective(directive)
    }
  } else if (event.key === " " && selectedIndex.value >= 0) {
    const directive = filtered.value[selectedIndex.value]
    if (directive && (event.target === document.body || event.target === document.documentElement)) {
      event.preventDefault()
      openQuickLook(directive)
    }
  }
}

onMounted(() => window.addEventListener("keydown", onGlobalKeydown))
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onGlobalKeydown)
  if (searchTimer) clearTimeout(searchTimer)
})

function ariaSort(key: DirectiveSortKey): "ascending" | "descending" | "none" {
  return props.state.sort === key ? (key === "name" ? "ascending" : "descending") : "none"
}

function sortIcon(key: DirectiveSortKey) {
  return props.state.sort === key ? ArrowDown : ArrowUp
}

</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">
    <DirectiveListHeader />

    <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <button
        type="button"
        class="flex min-h-[76px] min-w-0 flex-col justify-center gap-0.5 rounded-lg border border-warn/30 bg-surface-1 px-4 py-2.5 text-left transition-colors hover:border-warn/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        @click="update({ state: 'candidate' })"
      >
        <span class="flex items-center gap-1 text-xs leading-4 text-fg-3">
          <Clock :size="12" :stroke-width="1.8" aria-hidden="true" />
          Awaiting approval
        </span>
        <span class="ix-kpi" :class="stats.awaiting ? 'text-warn' : 'text-fg-1'">
          {{ stats.awaiting }}<span class="text-sm font-medium text-fg-3"> of {{ directives.length }}</span>
        </span>
        <span class="truncate text-xs leading-4 text-fg-3">
          {{ stats.oldestWaiting ? `oldest waits ${formatGovernWait(stats.oldestWaiting)}` : "nothing waiting" }}
        </span>
      </button>

      <button
        type="button"
        class="flex min-h-[76px] min-w-0 flex-col justify-center gap-0.5 rounded-lg border border-crit/30 bg-surface-1 px-4 py-2.5 text-left transition-colors hover:border-crit/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        @click="update({ state: 'candidate' })"
      >
        <span class="flex items-center gap-1 text-xs leading-4 text-fg-3">
          <ShieldAlert :size="12" :stroke-width="1.8" aria-hidden="true" />
          Failing checks
        </span>
        <span class="ix-kpi" :class="stats.failingChecks ? 'text-crit' : 'text-fg-1'">
          {{ stats.failingChecks }}
        </span>
        <span class="truncate text-xs leading-4 text-fg-3">{{ failingHint }}</span>
      </button>

      <div class="flex min-h-[76px] min-w-0 flex-col justify-center gap-0.5 rounded-lg border border-line-subtle bg-surface-1 px-4 py-2.5">
        <span class="flex items-center gap-1 text-xs leading-4 text-fg-3">
          <RotateCcw :size="12" :stroke-width="1.8" aria-hidden="true" />
          Changed · 7 days
        </span>
        <span class="ix-kpi text-fg-1">{{ stats.changedLast7Days }}</span>
        <span class="truncate text-xs leading-4 text-fg-3">{{ recentPromotionHint }}</span>
      </div>

      <div class="flex min-h-[76px] min-w-0 flex-col justify-center gap-0.5 rounded-lg border border-line-subtle bg-surface-1 px-4 py-2.5">
        <span class="text-xs leading-4 text-fg-3">Rollbacks · 30 days</span>
        <span class="ix-kpi text-fg-1">{{ stats.rollbacksLast30Days }}</span>
        <span class="truncate text-xs leading-4 text-fg-3">{{ recentRollbackHint }}</span>
      </div>
    </div>

    <div class="flex flex-col gap-2">
      <div class="flex flex-wrap items-center gap-2">
        <div class="relative min-w-52 flex-1 sm:max-w-xs">
          <Search :size="13" :stroke-width="1.9" class="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-fg-3" aria-hidden="true" />
          <input
            ref="searchInput"
            :value="searchDraft"
            type="search"
            placeholder="Search directives, agents, authors"
            aria-label="Search directives"
            class="ix-input h-8 pr-9 pl-8 text-xs"
            @input="onSearchInput(($event.target as HTMLInputElement).value)"
            @change="submitSearch"
          >
          <span class="pointer-events-none absolute inset-y-0 right-2 flex items-center"><KeyHint>/</KeyHint></span>
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <button
              type="button"
              class="inline-flex h-8 items-center gap-1.5 rounded-md border border-line-subtle bg-surface-1 px-2.5 text-xs text-fg-2 transition-colors hover:border-line hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
              aria-label="Filter directives by state"
            >
              State: {{ DIRECTIVE_STATE_FILTER_LABELS[state.state] }}
              <span class="font-mono text-[0.625rem] text-fg-3 tabular-nums">{{ stateCounts[state.state] }}</span>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" class="w-48 p-1.5">
            <DropdownMenuLabel class="px-2 py-1 text-[0.6875rem] font-medium text-fg-3">State</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              v-for="filter in DIRECTIVE_STATE_FILTERS"
              :key="filter"
              class="justify-between py-1.5 text-xs"
              @select="update({ state: filter })"
            >
              {{ DIRECTIVE_STATE_FILTER_LABELS[filter] }}
              <span class="font-mono text-[0.625rem] text-fg-3">{{ stateCounts[filter] }}</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <button
              type="button"
              class="inline-flex h-8 items-center gap-1.5 rounded-md border border-line-subtle bg-surface-1 px-2.5 text-xs text-fg-2 transition-colors hover:border-line hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
              aria-label="Filter directives by agent"
            >
              Agent: {{ state.agent === "all" ? "All agents" : agentOptions.find((option) => option.id === state.agent)?.name ?? "Unknown" }}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" class="w-56 p-1.5">
            <DropdownMenuItem class="py-1.5 text-xs" @select="update({ agent: 'all' })">All agents</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              v-for="option in agentOptions"
              :key="option.id"
              class="justify-between py-1.5 text-xs"
              @select="update({ agent: option.id })"
            >
              {{ option.name }}
              <span class="font-mono text-[0.625rem] text-fg-3">{{ option.count }}</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <button
              type="button"
              class="inline-flex h-8 items-center gap-1.5 rounded-md border border-line-subtle bg-surface-1 px-2.5 text-xs text-fg-2 transition-colors hover:border-line hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory sm:ml-auto"
              aria-label="Sort directives"
            >
              Sort: {{ DIRECTIVE_SORT_LABELS[state.sort] }}
              <component :is="state.sort === 'name' ? ArrowUp : ArrowDown" :size="11" :stroke-width="2" class="text-fg-3" aria-hidden="true" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" class="w-48 p-1.5">
            <DropdownMenuLabel class="px-2 py-1.5 text-xs font-semibold text-fg-1">Sort by</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              v-for="key in DIRECTIVE_SORT_KEYS"
              :key="key"
              class="justify-between py-1.5 text-xs"
              @select="update({ sort: key })"
            >
              {{ DIRECTIVE_SORT_LABELS[key] }}
              <span v-if="state.sort === key" class="font-mono text-[0.625rem] text-fg-3">selected</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <button
          v-if="activeFilters"
          type="button"
          class="inline-flex h-8 items-center gap-1 rounded-md px-2 text-xs text-fg-3 transition-colors hover:bg-surface-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
          @click="clearFilters"
        >
          <X :size="12" :stroke-width="2" aria-hidden="true" />
          Clear
        </button>

        <div class="ml-auto flex shrink-0 items-center gap-2 text-[0.6875rem] leading-4 text-fg-3">
          <span>
            Showing <span class="font-mono text-fg-2 tabular-nums">{{ filtered.length }}</span> of
            <span class="font-mono text-fg-2 tabular-nums">{{ directives.length }}</span>
          </span>
          <span aria-hidden="true">·</span>
          <span>{{ liveCount }} live</span>
        </div>
      </div>
    </div>

    <div class="hidden overflow-hidden rounded-lg border border-line-subtle bg-surface-1 min-[1280px]:block">
      <div class="ix-scroll overflow-x-auto">
        <table class="ix-agent-table" aria-label="Directive table">
          <thead>
            <tr>
              <th scope="col" class="!pl-4" :aria-sort="ariaSort('name')">
                <button type="button" class="ix-sort-button" @click="update({ sort: 'name' })">
                  Directive
                  <component :is="sortIcon('name')" :size="10" :stroke-width="2" :class="state.sort === 'name' ? 'text-fg-2' : 'text-fg-off'" aria-hidden="true" />
                </button>
              </th>
              <th scope="col" class="w-28">State</th>
              <th scope="col" class="w-32" :aria-sort="ariaSort('live')">
                <button type="button" class="ix-sort-button" @click="update({ sort: 'live' })">
                  Live
                  <component :is="sortIcon('live')" :size="10" :stroke-width="2" :class="state.sort === 'live' ? 'text-fg-2' : 'text-fg-off'" aria-hidden="true" />
                </button>
              </th>
              <th scope="col" class="w-36">Candidate</th>
              <th scope="col" class="w-24">
                Checks
                <span class="text-fg-3">(candidate)</span>
              </th>
              <th scope="col" class="w-28">Approval</th>
              <th scope="col" class="w-32" :aria-sort="ariaSort('change')">
                <button type="button" class="ix-sort-button" @click="update({ sort: 'change' })">
                  Last change
                  <component :is="sortIcon('change')" :size="10" :stroke-width="2" :class="state.sort === 'change' ? 'text-fg-2' : 'text-fg-off'" aria-hidden="true" />
                </button>
              </th>
              <th scope="col" class="w-40">Agents</th>
              <th scope="col" class="w-8"><span class="sr-only">Open</span></th>
            </tr>
          </thead>
          <tbody>
            <DirectiveResultRow
              v-for="directive in filtered"
              :key="directive.id"
              :data-directive-row="directive.id"
              :directive="directive"
              :return-to="returnTo"
              :selected="selectedId === directive.id"
              @open="openDirective(directive)"
              @quick="openQuickLook(directive)"
            />
          </tbody>
        </table>
      </div>
      <div v-if="filtered.length === 0" class="flex flex-col items-center gap-1 px-4 py-10 text-center">
        <p class="text-sm font-medium text-fg-1">No directives match this view</p>
        <p class="text-xs text-fg-3">Clear the search or state filter to return to the four records.</p>
        <button type="button" class="ix-button-secondary mt-2 h-8 px-3 text-xs" @click="clearFilters">Clear filters</button>
      </div>
    </div>

    <div class="flex flex-col gap-2 min-[1280px]:hidden">
      <DirectiveResultCard
        v-for="directive in filtered"
        :key="directive.id"
        :directive="directive"
        @open="openDirective(directive)"
        @quick="openQuickLook(directive)"
      />
      <div v-if="filtered.length === 0" class="rounded-lg border border-dashed border-line-subtle bg-surface-1/40 px-4 py-8 text-center">
        <p class="text-sm font-medium text-fg-1">No directives match this view</p>
        <button type="button" class="ix-button-secondary mt-2 h-8 px-3 text-xs" @click="clearFilters">Clear filters</button>
      </div>
    </div>

    <p class="flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.6875rem] leading-4 text-fg-3">
      <button type="button" class="hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory" @click="shortcutsDialog?.showModal()">
        Keyboard shortcuts <KeyHint>?</KeyHint>
      </button>
    </p>

    <Sheet :open="quickLookOpen" @update:open="closeQuickLook">
      <SheetContent side="right" class="w-[420px] overflow-y-auto sm:max-w-[420px] !p-0">
        <SheetHeader class="!p-0">
          <SheetTitle class="sr-only">Directive quick look</SheetTitle>
          <SheetDescription class="sr-only">A preview of the selected directive. Open the directive page for every tab.</SheetDescription>
        </SheetHeader>
        <DirectiveQuickLook
          v-if="quickLookDirective"
          :directive-id="quickLookDirective.id"
          :return-to="returnTo"
          @open="openDirective(quickLookDirective)"
        />
      </SheetContent>
    </Sheet>

    <dialog
      ref="shortcutsDialog"
      class="w-[min(26rem,calc(100vw-1.5rem))] max-w-none rounded-lg border border-line bg-overlay p-0 text-fg-1 shadow-2xl backdrop:bg-canvas/70"
      aria-labelledby="directive-shortcuts-title"
      @click="($event.target === shortcutsDialog) && shortcutsDialog?.close()"
    >
      <div class="flex items-start justify-between gap-3 border-b border-line-subtle px-4 py-3">
        <div>
          <p id="directive-shortcuts-title" class="text-sm font-semibold text-fg-1">Keyboard shortcuts</p>
          <p class="mt-0.5 text-xs text-fg-3">Directives list</p>
        </div>
        <button
          type="button"
          class="inline-flex size-6 items-center justify-center rounded text-fg-3 hover:bg-surface-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
          aria-label="Close shortcuts"
          @click="shortcutsDialog?.close()"
        >
          <X :size="13" :stroke-width="2" aria-hidden="true" />
        </button>
      </div>
      <dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 px-4 py-3 text-xs">
        <dt class="font-mono text-fg-2"><KeyHint>/</KeyHint></dt><dd class="text-fg-3">Focus search</dd>
        <dt class="font-mono text-fg-2"><KeyHint>j</KeyHint> <KeyHint>k</KeyHint></dt><dd class="text-fg-3">Move selection</dd>
        <dt class="font-mono text-fg-2"><KeyHint>Enter</KeyHint></dt><dd class="text-fg-3">Open the selected directive</dd>
        <dt class="font-mono text-fg-2"><KeyHint>Space</KeyHint></dt><dd class="text-fg-3">Quick look at the selected directive</dd>
        <dt class="font-mono text-fg-2"><KeyHint>Esc</KeyHint></dt><dd class="text-fg-3">Close or clear search</dd>
        <dt class="font-mono text-fg-2"><KeyHint>?</KeyHint></dt><dd class="text-fg-3">Show this dialog</dd>
      </dl>
    </dialog>
  </div>
</template>
