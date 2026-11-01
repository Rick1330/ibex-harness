<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router"
import { previewMemories, type PreviewMemory } from "@/lib/memory-preview"
import {
  emptyMemoryListState,
  memoryDetailHref,
  parseMemoryListQuery,
  serializeMemoryListQuery,
  type MemoryListState,
  type MemorySortKey,
  type MemoryView,
} from "@/lib/memory-list-query"
import {
  activeMemoryFilterChips,
  filterMemories,
  groupMemories,
  memoryNeedsReview,
  sortMemories,
  viewMatchesMemory,
} from "@/lib/memory-list"
import MemoryAttentionSummary from "./MemoryAttentionSummary.vue"
import MemoryFilterDrawer from "./MemoryFilterDrawer.vue"
import MemoryListEmpty from "./MemoryListEmpty.vue"
import MemoryListError from "./MemoryListError.vue"
import MemoryListFooter from "./MemoryListFooter.vue"
import MemoryListHeader from "./MemoryListHeader.vue"
import MemoryListSkeleton from "./MemoryListSkeleton.vue"
import MemoryListToolbar from "./MemoryListToolbar.vue"
import MemoryPeekPanel from "./MemoryPeekPanel.vue"
import MemoryResultCard from "./MemoryResultCard.vue"
import MemoryResultsTable from "./MemoryResultsTable.vue"
import MemorySelectionBar from "./MemorySelectionBar.vue"

const PAGE_SIZE = 25
const SNAPSHOT_KEY = "ibex:memory-list:return"

type Snapshot = {
  path: string
  scrollY: number
  activeId: string
  selected: string[]
}

const memories = previewMemories
const route = useRoute()
const router = useRouter()
const state = ref<MemoryListState>(parseMemoryListQuery(route.query))
const selectedIds = ref(new Set<string>())
const activeId = ref("")
const peekId = ref("")
const ready = ref(false)
const visibleCount = ref(PAGE_SIZE)
const retryKey = ref(0)
const filterDrawer = ref<InstanceType<typeof MemoryFilterDrawer> | null>(null)
const toolbar = ref<InstanceType<typeof MemoryListToolbar> | null>(null)
const resultsRoot = ref<HTMLElement | null>(null)

let searchTimer: ReturnType<typeof setTimeout> | null = null

const returnTo = computed(() => route.fullPath)
const agents = computed(() => [...new Set(memories.map((memory) => memory.agent))].sort((first, second) => first.localeCompare(second)))

const counts = computed<Record<MemoryView, number>>(() => ({
  all: memories.length,
  review: memories.filter(memoryNeedsReview).length,
  conflicts: memories.filter((memory) => viewMatchesMemory("conflicts", memory)).length,
  pinned: memories.filter((memory) => viewMatchesMemory("pinned", memory)).length,
  never: memories.filter((memory) => viewMatchesMemory("never", memory)).length,
  expiring: memories.filter((memory) => viewMatchesMemory("expiring", memory)).length,
  tombstoned: memories.filter((memory) => viewMatchesMemory("tombstoned", memory)).length,
}))

const filterResult = computed<{ memories: PreviewMemory[]; error: string | null }>(() => {
  void retryKey.value
  try {
    return { memories: filterMemories(memories, state.value), error: null }
  } catch (error) {
    return { memories: [], error: error instanceof Error ? error.message : "Unexpected rendering error." }
  }
})
const filtered = computed(() => filterResult.value.memories)
const renderError = computed(() => filterResult.value.error)

const sorted = computed(() => sortMemories(filtered.value, state.value.sort, state.value.direction))
const visibleMemories = computed(() => sorted.value.slice(0, visibleCount.value))
const groups = computed(() => groupMemories(visibleMemories.value, state.value.group))
const hasMore = computed(() => visibleCount.value < sorted.value.length)

const chips = computed(() => activeMemoryFilterChips(state.value))
const noResults = computed(() => ready.value && !renderError.value && filtered.value.length === 0)
const emptyWorkspace = computed(() => memories.length === 0)

const allSelected = computed(
  () => visibleMemories.value.length > 0 && visibleMemories.value.every((memory) => selectedIds.value.has(memory.id)),
)
const someSelected = computed(() => visibleMemories.value.some((memory) => selectedIds.value.has(memory.id)))

const peekMemory = computed(() => memories.find((memory) => memory.id === peekId.value) ?? null)

const updatedRange = computed(() => {
  if (filtered.value.length === 0) return null
  const stamps = filtered.value.map((memory) => Date.parse(memory.updatedAt))
  return {
    from: new Date(Math.min(...stamps)).toISOString(),
    to: new Date(Math.max(...stamps)).toISOString(),
  }
})

const resultsSummary = computed(() => {
  if (!ready.value) return "Loading memories"
  if (noResults.value) return "No memories match the current filters"
  return `${filtered.value.length} of ${memories.length} memories shown`
})

function serialized(value: MemoryListState): string {
  return serializeMemoryListQuery(value).toString()
}

function isSearchOnly(next: MemoryListState): boolean {
  const withoutSearch = (value: MemoryListState) => serialized({ ...value, search: "" })
  return withoutSearch(next) === withoutSearch(parseMemoryListQuery(route.query)) && next.search !== parseMemoryListQuery(route.query).search
}

function queryFrom(value: MemoryListState): Record<string, string> {
  return Object.fromEntries(serializeMemoryListQuery(value))
}

function navigate(method: "push" | "replace"): void {
  if (searchTimer) {
    clearTimeout(searchTimer)
    searchTimer = null
  }
  const next = serialized(state.value)
  if (next === serialized(parseMemoryListQuery(route.query))) return
  const done = () => {
    if (!import.meta.client) return
    void router[method]({ query: queryFrom(state.value) }).catch(() => undefined)
  }
  if (method === "replace") {
    searchTimer = setTimeout(done, 180)
  } else {
    done()
  }
}

watch(
  state,
  () => {
    if (import.meta.server) return
    if (activeId.value && !filtered.value.some((memory) => memory.id === activeId.value)) activeId.value = ""
    navigate(isSearchOnly(state.value) ? "replace" : "push")
  },
  { deep: true },
)

watch(
  () => route.query,
  () => {
    const parsed = parseMemoryListQuery(route.query)
    if (serialized(parsed) === serialized(state.value)) return
    state.value = parsed
  },
)

watch(
  () => serialized(state.value),
  () => {
    visibleCount.value = PAGE_SIZE
  },
)

function saveSnapshot(): void {
  if (!import.meta.client) return
  try {
    const snapshotValue: Snapshot = {
      path: route.fullPath,
      scrollY: window.scrollY,
      activeId: activeId.value,
      selected: [...selectedIds.value],
    }
    sessionStorage.setItem(SNAPSHOT_KEY, JSON.stringify(snapshotValue))
  } catch {
    /* session storage is optional */
  }
}

function restoreSnapshot(): void {
  if (!import.meta.client) return
  let stored: Snapshot | null = null
  try {
    const raw = sessionStorage.getItem(SNAPSHOT_KEY)
    sessionStorage.removeItem(SNAPSHOT_KEY)
    stored = raw ? (JSON.parse(raw) as Snapshot) : null
  } catch {
    stored = null
  }
  if (!stored) return
  if (stored.path !== route.fullPath) return
  selectedIds.value = new Set(stored.selected.filter((id) => memories.some((memory) => memory.id === id)))
  activeId.value = memories.some((memory) => memory.id === stored.activeId) ? stored.activeId : ""
  void nextTick(() => {
    window.scrollTo({ top: stored!.scrollY, behavior: "instant" })
    if (activeId.value) focusRow(activeId.value, false)
  })
}

function rowElements(): HTMLElement[] {
  const root = resultsRoot.value
  if (!root) return []
  return [...root.querySelectorAll<HTMLElement>("[data-memory-row], [data-memory-card]")]
}

function rowId(element: HTMLElement | undefined): string {
  return element?.dataset.memoryRow ?? element?.dataset.memoryCard ?? ""
}

function focusRow(id: string, scroll = true): void {
  const element = rowElements().find((row) => rowId(row) === id)
  if (!element) return
  element.focus({ preventScroll: !scroll })
  if (scroll) element.scrollIntoView({ block: "nearest" })
}

function openMemory(id: string): void {
  activeId.value = id
  saveSnapshot()
  void router.push(memoryDetailHref(id, returnTo.value)).catch(() => undefined)
}

function toggleOne(id: string): void {
  const next = new Set(selectedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedIds.value = next
  activeId.value = id
}

function toggleMany(ids: string[], selected: boolean): void {
  const next = new Set(selectedIds.value)
  for (const id of ids) {
    if (selected) next.add(id)
    else next.delete(id)
  }
  selectedIds.value = next
}

function toggleAll(): void {
  toggleMany(visibleMemories.value.map((memory) => memory.id), !allSelected.value)
}

function clearSelection(): void {
  selectedIds.value = new Set()
}

function setSort(key: MemorySortKey): void {
  if (state.value.sort === key) {
    state.value = { ...state.value, direction: state.value.direction === "asc" ? "desc" : "asc" }
    return
  }
  const direction = key === "content" || key === "type" || key === "agent" || key === "validity" ? "asc" : "desc"
  state.value = { ...state.value, sort: key, direction }
}

function clearFilters(): void {
  state.value = { ...state.value, search: "", filters: emptyMemoryListState().filters }
}

function applyFilters(filters: MemoryListState["filters"]): void {
  state.value = { ...state.value, filters }
}

function removeChip(index: number): void {
  const chip = chips.value[index]
  if (!chip) return
  state.value = { ...state.value, filters: chip.next }
}

function loadMore(): void {
  visibleCount.value = Math.min(sorted.value.length, visibleCount.value + PAGE_SIZE)
}

function retry(): void {
  retryKey.value += 1
  ready.value = false
  void nextTick(() => {
    ready.value = true
  })
}

function focusSearch(): void {
  toolbar.value?.focusSearch()
}

function moveActive(step: number): void {
  const rows = rowElements()
  if (rows.length === 0) return
  const current = rows.findIndex((row) => rowId(row) === activeId.value)
  const start = current < 0 ? (step > 0 ? -1 : rows.length) : current
  const next = rows[Math.min(rows.length - 1, Math.max(0, start + step))]
  if (!next) return
  const id = rowId(next)
  activeId.value = id
  next.focus()
  next.scrollIntoView({ block: "nearest" })
}

function isTypingTarget(target: EventTarget | null): boolean {
  return (
    target instanceof Element &&
    Boolean(target.closest("input, textarea, select, [contenteditable='true']"))
  )
}

function onGlobalKeydown(event: KeyboardEvent): void {
  if (event.defaultPrevented) return

  if (event.key === "/" && (event.metaKey || event.ctrlKey)) {
    event.preventDefault()
    focusSearch()
    return
  }

  if (event.metaKey || event.altKey) return
  const typing = isTypingTarget(event.target)

  if (event.key === "/" && !typing) {
    event.preventDefault()
    focusSearch()
    return
  }

  if (event.key === "Escape") {
    if (peekId.value) {
      closePeek()
      return
    }
    if (event.target instanceof HTMLElement && event.target.closest("dialog")) return
    if (selectedIds.value.size > 0) {
      clearSelection()
      return
    }
    return
  }

  if (typing) return

  if (event.key === "j" || event.key === "ArrowDown") {
    event.preventDefault()
    moveActive(1)
    return
  }
  if (event.key === "k" || event.key === "ArrowUp") {
    event.preventDefault()
    moveActive(-1)
    return
  }

  const rows = rowElements()
  const activeRow = rows.find((row) => rowId(row) === activeId.value) ?? null
  if (!activeId.value) return

  if (event.key === "Enter") {
    if (event.target === document.body || activeRow === event.target) {
      event.preventDefault()
      openMemory(activeId.value)
    }
  } else if (event.key === " " || event.key === "Spacebar") {
    if (event.target === document.body || activeRow === event.target) {
      event.preventDefault()
      peekId.value = activeId.value
    }
  } else if (event.key === "x" || event.key === "X") {
    event.preventDefault()
    toggleOne(activeId.value)
  }
}

function closePeek(): void {
  const id = peekId.value
  peekId.value = ""
  if (id) void nextTick(() => focusRow(id, false))
}

watch(peekId, (value) => {
  if (!value) return
  activeId.value = value
})

function onResultsFocus(event: FocusEvent): void {
  const target = event.target
  if (!(target instanceof HTMLElement)) return
  const id = target.dataset.memoryRow ?? target.dataset.memoryCard ?? (target.closest("[data-memory-row], [data-memory-card]") as HTMLElement | null)?.dataset.memoryRow
  if (id) activeId.value = id
}

onMounted(() => {
  window.addEventListener("keydown", onGlobalKeydown)
  ready.value = true
  restoreSnapshot()
})

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onGlobalKeydown)
  if (searchTimer) clearTimeout(searchTimer)
})

onBeforeRouteLeave(() => {
  saveSnapshot()
})
</script>

<template>
  <div class="flex min-w-0 flex-col gap-2.5">
    <MemoryListHeader :total="memories.length" :agent-count="agents.length" :records="filtered" />

    <MemoryAttentionSummary :memories="memories" @select-view="state.view = $event" />

    <div class="sticky top-0 z-20 -mx-1 bg-canvas/95 px-1 backdrop-blur-sm">
      <MemoryListToolbar
        ref="toolbar"
        v-model="state"
        :counts="counts"
        :total="memories.length"
        :result-count="filtered.length"
        @open-filters="filterDrawer?.open()"
        @copy-link="saveSnapshot"
      />
    </div>

    <div ref="resultsRoot" class="min-w-0" @focusin="onResultsFocus">
      <MemoryListError v-if="renderError" :message="renderError" @retry="retry" />

      <MemoryListSkeleton v-else-if="!ready" :density="state.density" />

      <MemoryListEmpty
        v-else-if="emptyWorkspace"
        mode="empty-workspace"
        @clear="clearFilters"
      />

      <MemoryListEmpty
        v-else-if="noResults"
        mode="no-results"
        :chips="chips"
        :search="state.search"
        @clear="clearFilters"
        @remove-chip="removeChip(chips.indexOf($event))"
      />

      <template v-else>
        <MemoryResultsTable
          class="hidden lg:block"
          :groups="groups"
          :selected-ids="selectedIds"
          :active-id="activeId"
          :density="state.density"
          :columns="state.columns"
          :show-tags="state.showTags"
          :query="state.search"
          :return-to="returnTo"
          :sort="state.sort"
          :direction="state.direction"
          :all-selected="allSelected"
          :some-selected="someSelected"
          @open="openMemory"
          @peek="peekId = $event"
          @toggle="toggleOne"
          @toggle-all="toggleAll"
          @toggle-many="toggleMany"
          @sort="setSort"
        />

        <div class="space-y-3 lg:hidden" aria-label="Memory list">
          <section v-for="group in groups" :key="group.key" class="min-w-0">
            <h2
              v-if="group.label"
              class="mb-1.5 flex items-baseline gap-2 px-0.5 text-xs font-medium text-fg-3"
            >
              {{ group.label }}
              <span class="font-mono text-[0.625rem] text-fg-2 tabular-nums">{{ group.rows.length }}</span>
            </h2>
            <ul class="space-y-2">
              <MemoryResultCard
                v-for="memory in group.rows"
                :key="memory.id"
                :memory="memory"
                :selected="selectedIds.has(memory.id)"
                :active="activeId === memory.id"
                :query="state.search"
                :return-to="returnTo"
                @open="openMemory"
                @peek="peekId = $event"
                @toggle="toggleOne"
              />
            </ul>
          </section>
        </div>

        <MemoryListFooter
          :total="filtered.length"
          :visible="visibleMemories.length"
          :updated-range="updatedRange"
          :has-more="hasMore"
          @load-more="loadMore"
        />
      </template>
    </div>

    <p class="sr-only" role="status" aria-live="polite">{{ resultsSummary }}</p>

    <MemorySelectionBar v-if="selectedIds.size > 0" :count="selectedIds.size" @clear="clearSelection" />

    <MemoryPeekPanel v-if="peekMemory" :memory="peekMemory" :return-to="returnTo" @close="closePeek" />

    <MemoryFilterDrawer
      ref="filterDrawer"
      :memories="memories"
      :state="state"
      :result-count="filtered.length"
      @apply="applyFilters"
      @reset="clearFilters"
    />
  </div>
</template>
