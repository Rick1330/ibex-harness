<script setup lang="ts">
import { computed, ref } from "vue"
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronDown,
  Columns3,
  Layers,
  Link2,
  Lock,
  Plus,
  RotateCcw,
  Rows3,
  Rows4,
  Search,
  SlidersHorizontal,
} from "@lucide/vue"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { emptyMemoryFilters } from "@/lib/memory-preview"
import {
  MEMORY_DEFAULT_SORT_DIRECTION,
  MEMORY_GROUP_LABELS,
  MEMORY_OPTIONAL_COLUMN_LABELS,
  MEMORY_OPTIONAL_COLUMNS,
  MEMORY_SORT_LABELS,
  type MemoryGroupKey,
  type MemoryListState,
  type MemoryOptionalColumn,
  type MemorySortKey,
  type MemoryView,
} from "@/lib/memory-list-query"
import { activeMemoryFilterChips, activeMemoryFilterCount, memoryViewIsModified } from "@/lib/memory-list"
import MemoryFilterChip from "./primitives/MemoryFilterChip.vue"
import MemoryKbd from "./primitives/MemoryKbd.vue"
import MemoryViewTabs from "./MemoryViewTabs.vue"

const state = defineModel<MemoryListState>({ required: true })

defineProps<{
  counts: Record<MemoryView, number>
  total: number
  resultCount: number
}>()

const emit = defineEmits<{
  openFilters: []
  copyLink: []
  resetDisplay: []
}>()

const searchInput = ref<HTMLInputElement | null>(null)

const modified = computed(() => memoryViewIsModified(state.value))
const filterCount = computed(() => activeMemoryFilterCount(state.value))
const chips = computed(() => activeMemoryFilterChips(state.value))
const sortArrow = computed(() => (state.value.direction === "asc" ? ArrowUp : ArrowDown))

function setView(view: MemoryView): void {
  state.value = { ...state.value, view, search: "", filters: emptyMemoryFilters() }
}

function setSearch(value: string): void {
  state.value = { ...state.value, search: value }
}

function setSortField(key: MemorySortKey): void {
  state.value = {
    ...state.value,
    sort: key,
    direction: MEMORY_DEFAULT_SORT_DIRECTION[key],
  }
}

function toggleSortDirection(): void {
  state.value = {
    ...state.value,
    direction: state.value.direction === "asc" ? "desc" : "asc",
  }
}

function setGroup(group: MemoryGroupKey): void {
  state.value = { ...state.value, group }
}

function setDensity(density: MemoryListState["density"]): void {
  state.value = { ...state.value, density }
}

function toggleColumn(column: MemoryOptionalColumn): void {
  const next = new Set(state.value.columns)
  if (next.has(column)) next.delete(column)
  else next.add(column)
  state.value = { ...state.value, columns: [...next] }
}

function toggleTags(): void {
  state.value = { ...state.value, showTags: !state.value.showTags }
}

function resetDisplay(): void {
  state.value = { ...state.value, density: "comfortable", columns: [], showTags: true }
  emit("resetDisplay")
}

function removeChip(next: MemoryListState["filters"]): void {
  state.value = { ...state.value, filters: next }
}

function clearAll(): void {
  state.value = { ...state.value, search: "", filters: emptyMemoryFilters() }
}

function focusSearch(): void {
  searchInput.value?.focus()
  searchInput.value?.select()
}

defineExpose({ focusSearch })
</script>

<template>
  <div>
    <div class="flex items-end justify-between gap-3 border-b border-line-subtle">
      <MemoryViewTabs
        :view="state.view"
        :counts="counts"
        :modified="modified"
        @select="setView"
      />
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <button
            type="button"
            class="mb-1.5 inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2 text-xs font-medium text-fg-3 transition-colors hover:bg-surface-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            aria-label="Create or manage views"
          >
            <Plus :size="13" :stroke-width="1.9" aria-hidden="true" />
            <span class="max-sm:sr-only">View</span>
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" class="w-64 p-1.5">
          <DropdownMenuLabel class="px-2 py-1.5 text-xs font-semibold text-fg-1">Saved views</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem class="gap-2 py-1.5 text-xs" @select="emit('copyLink')">
            <Link2 :size="13" :stroke-width="1.8" aria-hidden="true" />
            Copy link to this view
          </DropdownMenuItem>
          <DropdownMenuItem disabled class="gap-2 py-1.5 text-xs">
            <Lock :size="13" :stroke-width="1.8" aria-hidden="true" />
            Save current view
          </DropdownMenuItem>
          <p class="px-2 pt-1 pb-1.5 text-[0.6875rem] leading-4 text-fg-3">
            Saving custom views needs a privileged write contract. The URL is the current view.
          </p>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>

    <div class="flex flex-wrap items-center gap-2 py-1">
      <div class="relative min-w-[13rem] flex-1 sm:max-w-[26rem]">
        <Search
          :size="15"
          :stroke-width="1.8"
          class="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-fg-3"
          aria-hidden="true"
        />
        <input
          ref="searchInput"
          :value="state.search"
          type="search"
          class="h-8 w-full rounded-md border border-line-subtle bg-surface-1 pr-10 pl-8 text-sm text-fg-1 transition-colors placeholder:text-fg-3 hover:border-line focus:border-accent-memory focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
          placeholder="Search statements, IDs, tags, sessions"
          aria-label="Search memories"
          @input="setSearch(($event.target as HTMLInputElement).value)"
        >
        <span class="pointer-events-none absolute inset-y-0 right-2 flex items-center">
          <MemoryKbd>/</MemoryKbd>
        </span>
      </div>

      <button
        type="button"
        class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        :class="filterCount ? 'border-accent-memory/35 bg-memory-tint text-memory hover:border-accent-memory/55' : 'border-line-subtle bg-surface-1 text-fg-2 hover:border-line hover:text-fg-1'"
        :aria-label="filterCount ? `Filters, ${filterCount} active` : 'Filters'"
        @click="emit('openFilters')"
      >
        <SlidersHorizontal :size="13" :stroke-width="1.8" aria-hidden="true" />
        Filter
        <span v-if="filterCount" class="rounded-full bg-surface-1 px-1.5 py-0.5 font-mono text-[0.625rem] leading-none">{{ filterCount }}</span>
      </button>

      <span class="mx-0.5 h-5 w-px bg-line-subtle max-lg:hidden" aria-hidden="true" />

      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <button
            type="button"
            class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2 text-xs text-fg-2 transition-colors hover:bg-surface-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            aria-label="Group memories"
          >
            <Layers :size="13" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
            <span class="text-fg-3">Group:</span>
            {{ MEMORY_GROUP_LABELS[state.group] }}
            <ChevronDown :size="11" :stroke-width="1.9" class="text-fg-3" aria-hidden="true" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" class="w-44 p-1.5">
          <DropdownMenuLabel class="px-2 py-1.5 text-xs font-semibold text-fg-1">Group by</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuRadioGroup :model-value="state.group" @update:model-value="setGroup($event as MemoryGroupKey)">
            <DropdownMenuRadioItem v-for="(label, key) in MEMORY_GROUP_LABELS" :key="key" :value="key" class="py-1.5 text-xs">
              {{ label }}
            </DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>

      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <button
            type="button"
            class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2 text-xs text-fg-2 transition-colors hover:bg-surface-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            aria-label="Sort memories"
          >
            <ArrowUpDown :size="13" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
            <span class="text-fg-3">Sort:</span>
            {{ MEMORY_SORT_LABELS[state.sort] }}
            <component :is="sortArrow" :size="11" :stroke-width="2" class="text-fg-3" aria-hidden="true" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" class="w-52 p-1.5">
          <DropdownMenuLabel class="px-2 py-1.5 text-xs font-semibold text-fg-1">Sort by</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuRadioGroup :model-value="state.sort" @update:model-value="setSortField($event as MemorySortKey)">
            <DropdownMenuRadioItem v-for="(label, key) in MEMORY_SORT_LABELS" :key="key" :value="key" class="py-1.5 text-xs">
              {{ label }}
            </DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem class="gap-2 py-1.5 text-xs" @select="toggleSortDirection">
            <component :is="sortArrow" :size="13" :stroke-width="1.8" aria-hidden="true" />
            {{ state.direction === "asc" ? "Ascending" : "Descending" }}
            <span class="ml-auto text-fg-3">Toggle</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <button
            type="button"
            class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2 text-xs text-fg-2 transition-colors hover:bg-surface-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            aria-label="Display options"
          >
            <Columns3 :size="13" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
            <span class="text-fg-3 max-sm:sr-only">Display</span>
            <ChevronDown :size="11" :stroke-width="1.9" class="text-fg-3" aria-hidden="true" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" class="w-64 p-1.5">
          <DropdownMenuLabel class="px-2 py-1.5 text-xs font-semibold text-fg-1">Density</DropdownMenuLabel>
          <DropdownMenuRadioGroup :model-value="state.density" @update:model-value="setDensity($event as MemoryListState['density'])">
            <DropdownMenuRadioItem value="comfortable" class="gap-2 py-1.5 text-xs">
              <Rows3 :size="13" :stroke-width="1.8" aria-hidden="true" />
              Comfortable · 52px
            </DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="compact" class="gap-2 py-1.5 text-xs">
              <Rows4 :size="13" :stroke-width="1.8" aria-hidden="true" />
              Compact · 36px
            </DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
          <DropdownMenuSeparator />
          <DropdownMenuLabel class="px-2 py-1.5 text-xs font-semibold text-fg-1">Visible columns</DropdownMenuLabel>
          <DropdownMenuCheckboxItem
            v-for="column in MEMORY_OPTIONAL_COLUMNS"
            :key="column"
            :model-value="state.columns.includes(column)"
            class="py-1.5 text-xs"
            @update:model-value="toggleColumn(column)"
          >
            {{ MEMORY_OPTIONAL_COLUMN_LABELS[column] }}
          </DropdownMenuCheckboxItem>
          <DropdownMenuSeparator />
          <DropdownMenuCheckboxItem :model-value="state.showTags" class="py-1.5 text-xs" @update:model-value="toggleTags">
            Show tags in the memory cell
          </DropdownMenuCheckboxItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem class="gap-2 py-1.5 text-xs" @select="resetDisplay">
            <RotateCcw :size="13" :stroke-width="1.8" aria-hidden="true" />
            Reset display
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <span class="ml-auto flex shrink-0 items-center gap-1.5 pl-2 text-[0.6875rem] text-fg-3">
        Showing <span class="font-mono text-fg-2 tabular-nums">{{ resultCount }}</span> of
        <span class="font-mono text-fg-2 tabular-nums">{{ total }}</span>
      </span>
    </div>

    <div v-if="chips.length" class="flex flex-wrap items-center gap-1.5 border-t border-line-subtle py-1.5">
      <span class="mr-0.5 text-[0.6875rem] text-fg-3">Filters</span>
      <MemoryFilterChip
        v-for="chip in chips"
        :key="chip.key"
        :field="chip.field"
        :value="chip.value"
        @remove="removeChip(chip.next)"
      />
      <button
        type="button"
        class="ml-1 text-[0.6875rem] text-fg-3 underline underline-offset-2 transition-colors hover:text-fg-1"
        @click="clearAll"
      >
        Clear all
      </button>
    </div>
  </div>
</template>
