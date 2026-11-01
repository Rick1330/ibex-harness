<script setup lang="ts">
import { computed, ref } from "vue"
import { ChevronDown, RotateCcw, SlidersHorizontal, X } from "@lucide/vue"
import {
  MEMORY_CATEGORIES,
  MEMORY_CATEGORY_LABELS,
  MEMORY_SOURCES,
  MEMORY_SOURCE_LABELS,
  MEMORY_STATUSES,
  MEMORY_STATUS_LABELS,
  MEMORY_VISIBILITIES,
  MEMORY_VISIBILITY_LABELS,
  type MemoryFilterState,
  type PreviewMemory,
} from "@/lib/memory-preview"
import type { MemoryListState } from "@/lib/memory-list-query"

const props = defineProps<{
  memories: PreviewMemory[]
  state: MemoryListState
  resultCount: number
}>()

const emit = defineEmits<{
  apply: [filters: MemoryFilterState]
  reset: []
}>()

const dialog = ref<HTMLDialogElement | null>(null)
const closeButton = ref<HTMLButtonElement | null>(null)

type Facet = { value: string; label: string; count: number }

function facetCount(predicate: (memory: PreviewMemory) => boolean): number {
  return props.memories.filter(predicate).length
}

const categoryFacets = computed<Facet[]>(() =>
  MEMORY_CATEGORIES.map((value) => ({
    value,
    label: MEMORY_CATEGORY_LABELS[value],
    count: facetCount((memory) => memory.labels.some((label) => label.label === value)),
  })),
)

const statusFacets = computed<Facet[]>(() =>
  MEMORY_STATUSES.map((value) => ({
    value,
    label: MEMORY_STATUS_LABELS[value],
    count: facetCount((memory) => memory.status === value),
  })),
)

const visibilityFacets = computed<Facet[]>(() =>
  MEMORY_VISIBILITIES.map((value) => ({
    value,
    label: MEMORY_VISIBILITY_LABELS[value],
    count: facetCount((memory) => memory.visibility === value),
  })),
)

const sourceFacets = computed<Facet[]>(() =>
  MEMORY_SOURCES.map((value) => ({
    value,
    label: MEMORY_SOURCE_LABELS[value],
    count: facetCount((memory) => memory.source === value),
  })),
)

const agentFacets = computed<Facet[]>(() => {
  const counts = new Map<string, number>()
  for (const memory of props.memories) counts.set(memory.agent, (counts.get(memory.agent) ?? 0) + 1)
  return [...counts.entries()]
    .sort((first, second) => second[1] - first[1] || first[0].localeCompare(second[0]))
    .map(([value, count]) => ({ value, label: value, count }))
})

const tagFacets = computed<Facet[]>(() => {
  const counts = new Map<string, number>()
  for (const memory of props.memories) {
    for (const tag of memory.tags) counts.set(tag, (counts.get(tag) ?? 0) + 1)
  }
  return [...counts.entries()]
    .sort((first, second) => second[1] - first[1] || first[0].localeCompare(second[0]))
    .map(([value, count]) => ({ value, label: value, count }))
})

const safetyFacets: Facet[] = [
  { value: "pii", label: "PII detected", count: facetCount((memory) => memory.piiDetected) },
  { value: "injection", label: "Injection risk", count: facetCount((memory) => memory.injectionRisk >= 0.5) },
  { value: "conflict", label: "Open conflict", count: facetCount((memory) => memory.conflict?.state === "open") },
]

const confidenceOptions = [
  { value: "", label: "Any confidence" },
  { value: "high", label: "High · 0.90+" },
  { value: "medium", label: "Medium · 0.75–0.89" },
  { value: "low", label: "Low · below 0.75" },
]

const validityOptions = [
  { value: "", label: "Any validity" },
  { value: "open", label: "Open" },
  { value: "expiring", label: "Expiring · 30 days" },
  { value: "expired", label: "Expired" },
]

const retrievalOptions = [
  { value: "", label: "Any retrieval" },
  { value: "never", label: "Never retrieved" },
  { value: "24h", label: "Last 24 hours" },
  { value: "7d", label: "Last 7 days" },
  { value: "frequent", label: "Frequently retrieved · 50+" },
]

type ListKey = "categories" | "statuses" | "visibilities" | "sources" | "safety" | "tags"

function toggle(key: ListKey, value: string): void {
  const current = props.state.filters[key] as string[]
  const next = new Set(current)
  if (next.has(value)) next.delete(value)
  else next.add(value)
  emit("apply", { ...props.state.filters, [key]: [...next] } as MemoryFilterState)
}

function setValue<K extends "confidence" | "validity" | "retrieval" | "agent">(
  key: K,
  value: MemoryFilterState[K],
): void {
  emit("apply", { ...props.state.filters, [key]: value })
}

function setSelect(key: "confidence" | "validity" | "retrieval", event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  emit("apply", { ...props.state.filters, [key]: value } as MemoryFilterState)
}

function open(): void {
  if (!dialog.value?.open) dialog.value?.showModal()
  closeButton.value?.focus()
}

function close(): void {
  dialog.value?.close()
}

function onBackdrop(event: MouseEvent): void {
  if (event.target === dialog.value) close()
}

defineExpose({ open, close })
</script>

<template>
  <dialog
    ref="dialog"
    class="ix-scroll-dialog h-[100dvh] max-h-none w-[min(23rem,calc(100vw-1rem))] max-w-none border-0 bg-transparent p-0 text-fg-1"
    aria-label="Memory filters"
    @click="onBackdrop"
  >
    <div class="flex h-full flex-col border-l border-line bg-overlay">
      <div class="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-line-subtle px-4">
        <p class="flex items-center gap-1.5 text-sm font-semibold text-fg-1">
          <SlidersHorizontal :size="15" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
          Filters
        </p>
        <button
          ref="closeButton"
          type="button"
          class="inline-flex size-8 items-center justify-center rounded-md text-fg-3 transition-colors hover:bg-surface-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
          aria-label="Close filters"
          @click="close"
        >
          <X :size="16" :stroke-width="1.8" aria-hidden="true" />
        </button>
      </div>

      <div class="ix-scroll min-h-0 flex-1 overflow-y-auto px-3 py-2">
        <details open class="group/fs border-b border-line-subtle py-2.5">
          <summary class="flex cursor-pointer list-none items-center justify-between gap-2 rounded px-1 py-1 text-xs font-medium text-fg-1 [&::-webkit-details-marker]:hidden">
            <span class="flex items-center gap-1.5">
              Category
              <span class="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[0.625rem] text-fg-3">{{ state.filters.categories.length || "all" }}</span>
            </span>
            <ChevronDown :size="13" :stroke-width="1.8" class="text-fg-3 transition-transform group-open/fs:rotate-180" aria-hidden="true" />
          </summary>
          <div class="mt-1.5 space-y-0.5">
            <label v-for="facet in categoryFacets" :key="facet.value" class="flex h-8 cursor-pointer items-center gap-2 rounded px-1.5 text-xs text-fg-2 transition-colors hover:bg-surface-2">
              <input
                type="checkbox"
                class="size-3.5 rounded border-line accent-[var(--ix-accent-memory)]"
                :checked="state.filters.categories.includes(facet.value as never)"
                @change="toggle('categories', facet.value)"
              >
              <span class="min-w-0 flex-1 truncate">{{ facet.label }}</span>
              <span class="font-mono text-[0.625rem] text-fg-3 tabular-nums">{{ facet.count }}</span>
            </label>
          </div>
        </details>

        <details open class="group/fs border-b border-line-subtle py-2.5">
          <summary class="flex cursor-pointer list-none items-center justify-between gap-2 rounded px-1 py-1 text-xs font-medium text-fg-1 [&::-webkit-details-marker]:hidden">
            <span class="flex items-center gap-1.5">
              Lifecycle
              <span class="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[0.625rem] text-fg-3">{{ state.filters.statuses.length || "all" }}</span>
            </span>
            <ChevronDown :size="13" :stroke-width="1.8" class="text-fg-3 transition-transform group-open/fs:rotate-180" aria-hidden="true" />
          </summary>
          <div class="mt-1.5 space-y-0.5">
            <label v-for="facet in statusFacets" :key="facet.value" class="flex h-8 cursor-pointer items-center gap-2 rounded px-1.5 text-xs text-fg-2 transition-colors hover:bg-surface-2">
              <input
                type="checkbox"
                class="size-3.5 rounded border-line accent-[var(--ix-accent-memory)]"
                :checked="state.filters.statuses.includes(facet.value as never)"
                @change="toggle('statuses', facet.value)"
              >
              <span class="min-w-0 flex-1 truncate">{{ facet.label }}</span>
              <span class="font-mono text-[0.625rem] text-fg-3 tabular-nums">{{ facet.count }}</span>
            </label>
          </div>
        </details>

        <details class="group/fs border-b border-line-subtle py-2.5">
          <summary class="flex cursor-pointer list-none items-center justify-between gap-2 rounded px-1 py-1 text-xs font-medium text-fg-1 [&::-webkit-details-marker]:hidden">
            <span class="flex items-center gap-1.5">
              Lifecycle flags
              <span class="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[0.625rem] text-fg-3">{{ state.filters.safety.length || "all" }}</span>
            </span>
            <ChevronDown :size="13" :stroke-width="1.8" class="text-fg-3 transition-transform group-open/fs:rotate-180" aria-hidden="true" />
          </summary>
          <div class="mt-1.5 space-y-0.5">
            <label v-for="facet in safetyFacets" :key="facet.value" class="flex h-8 cursor-pointer items-center gap-2 rounded px-1.5 text-xs text-fg-2 transition-colors hover:bg-surface-2">
              <input
                type="checkbox"
                class="size-3.5 rounded border-line accent-[var(--ix-accent-memory)]"
                :checked="state.filters.safety.includes(facet.value as never)"
                @change="toggle('safety', facet.value)"
              >
              <span class="min-w-0 flex-1 truncate">{{ facet.label }}</span>
              <span class="font-mono text-[0.625rem] text-fg-3 tabular-nums">{{ facet.count }}</span>
            </label>
          </div>
        </details>

        <details class="group/fs border-b border-line-subtle py-2.5">
          <summary class="flex cursor-pointer list-none items-center justify-between gap-2 rounded px-1 py-1 text-xs font-medium text-fg-1 [&::-webkit-details-marker]:hidden">
            <span class="flex items-center gap-1.5">
              Scope
              <span class="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[0.625rem] text-fg-3">{{ state.filters.visibilities.length || "all" }}</span>
            </span>
            <ChevronDown :size="13" :stroke-width="1.8" class="text-fg-3 transition-transform group-open/fs:rotate-180" aria-hidden="true" />
          </summary>
          <div class="mt-1.5 space-y-0.5">
            <label v-for="facet in visibilityFacets" :key="facet.value" class="flex h-8 cursor-pointer items-center gap-2 rounded px-1.5 text-xs text-fg-2 transition-colors hover:bg-surface-2">
              <input
                type="checkbox"
                class="size-3.5 rounded border-line accent-[var(--ix-accent-memory)]"
                :checked="state.filters.visibilities.includes(facet.value as never)"
                @change="toggle('visibilities', facet.value)"
              >
              <span class="min-w-0 flex-1 truncate">{{ facet.label }}</span>
              <span class="font-mono text-[0.625rem] text-fg-3 tabular-nums">{{ facet.count }}</span>
            </label>
          </div>
        </details>

        <details class="group/fs border-b border-line-subtle py-2.5">
          <summary class="flex cursor-pointer list-none items-center justify-between gap-2 rounded px-1 py-1 text-xs font-medium text-fg-1 [&::-webkit-details-marker]:hidden">
            <span class="flex items-center gap-1.5">
              Source
              <span class="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[0.625rem] text-fg-3">{{ state.filters.sources.length || "all" }}</span>
            </span>
            <ChevronDown :size="13" :stroke-width="1.8" class="text-fg-3 transition-transform group-open/fs:rotate-180" aria-hidden="true" />
          </summary>
          <div class="mt-1.5 space-y-0.5">
            <label v-for="facet in sourceFacets" :key="facet.value" class="flex h-8 cursor-pointer items-center gap-2 rounded px-1.5 text-xs text-fg-2 transition-colors hover:bg-surface-2">
              <input
                type="checkbox"
                class="size-3.5 rounded border-line accent-[var(--ix-accent-memory)]"
                :checked="state.filters.sources.includes(facet.value as never)"
                @change="toggle('sources', facet.value)"
              >
              <span class="min-w-0 flex-1 truncate">{{ facet.label }}</span>
              <span class="font-mono text-[0.625rem] text-fg-3 tabular-nums">{{ facet.count }}</span>
            </label>
          </div>
        </details>

        <div class="border-b border-line-subtle py-2.5">
          <label class="block px-1 text-xs font-medium text-fg-1" for="memory-filter-agent">Agent</label>
          <select
            id="memory-filter-agent"
            class="mt-1.5 h-8 w-full rounded-md border border-line-subtle bg-surface-2 px-2 text-xs text-fg-2 focus:border-accent-memory focus:outline-none"
            :value="state.filters.agent"
            @change="setValue('agent', ($event.target as HTMLSelectElement).value)"
          >
            <option value="">Any agent</option>
            <option v-for="facet in agentFacets" :key="facet.value" :value="facet.value">{{ facet.label }} · {{ facet.count }}</option>
          </select>
        </div>

        <div class="border-b border-line-subtle py-2.5">
          <label class="block px-1 text-xs font-medium text-fg-1" for="memory-filter-confidence">Confidence</label>
          <select
            id="memory-filter-confidence"
            class="mt-1.5 h-8 w-full rounded-md border border-line-subtle bg-surface-2 px-2 text-xs text-fg-2 focus:border-accent-memory focus:outline-none"
            :value="state.filters.confidence"
            @change="setSelect('confidence', $event)"
          >
            <option v-for="option in confidenceOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </div>

        <div class="border-b border-line-subtle py-2.5">
          <label class="block px-1 text-xs font-medium text-fg-1" for="memory-filter-validity">Validity</label>
          <select
            id="memory-filter-validity"
            class="mt-1.5 h-8 w-full rounded-md border border-line-subtle bg-surface-2 px-2 text-xs text-fg-2 focus:border-accent-memory focus:outline-none"
            :value="state.filters.validity"
            @change="setSelect('validity', $event)"
          >
            <option v-for="option in validityOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </div>

        <div class="border-b border-line-subtle py-2.5">
          <label class="block px-1 text-xs font-medium text-fg-1" for="memory-filter-retrieval">Retrieved</label>
          <select
            id="memory-filter-retrieval"
            class="mt-1.5 h-8 w-full rounded-md border border-line-subtle bg-surface-2 px-2 text-xs text-fg-2 focus:border-accent-memory focus:outline-none"
            :value="state.filters.retrieval"
            @change="setSelect('retrieval', $event)"
          >
            <option v-for="option in retrievalOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </div>

        <details class="group/fs py-2.5">
          <summary class="flex cursor-pointer list-none items-center justify-between gap-2 rounded px-1 py-1 text-xs font-medium text-fg-1 [&::-webkit-details-marker]:hidden">
            <span class="flex items-center gap-1.5">
              Tags
              <span class="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[0.625rem] text-fg-3">{{ state.filters.tags.length || "all" }}</span>
            </span>
            <ChevronDown :size="13" :stroke-width="1.8" class="text-fg-3 transition-transform group-open/fs:rotate-180" aria-hidden="true" />
          </summary>
          <div class="mt-1.5 max-h-64 space-y-0.5 overflow-y-auto">
            <label v-for="facet in tagFacets" :key="facet.value" class="flex h-7 cursor-pointer items-center gap-2 rounded px-1.5 text-xs text-fg-2 transition-colors hover:bg-surface-2">
              <input
                type="checkbox"
                class="size-3.5 rounded border-line accent-[var(--ix-accent-memory)]"
                :checked="state.filters.tags.includes(facet.value)"
                @change="toggle('tags', facet.value)"
              >
              <span class="min-w-0 flex-1 truncate">{{ facet.label }}</span>
              <span class="font-mono text-[0.625rem] text-fg-3 tabular-nums">{{ facet.count }}</span>
            </label>
          </div>
        </details>
      </div>

      <div class="flex shrink-0 items-center gap-2 border-t border-line-subtle p-3">
        <button
          type="button"
          class="inline-flex h-9 flex-1 items-center justify-center gap-1.5 rounded-md border border-line-subtle bg-surface-1 text-xs font-medium text-fg-2 transition-colors hover:border-line hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
          @click="emit('reset')"
        >
          <RotateCcw :size="13" :stroke-width="1.8" aria-hidden="true" />
          Reset
        </button>
        <button
          type="button"
          class="inline-flex h-9 flex-1 items-center justify-center rounded-md bg-accent-memory text-xs font-semibold text-canvas transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
          @click="close"
        >
          Show {{ resultCount }} {{ resultCount === 1 ? "memory" : "memories" }}
        </button>
      </div>
    </div>
  </dialog>
</template>

<style scoped>
.ix-scroll-dialog {
  margin: 0 0 0 auto;
  padding: 0;
}

.ix-scroll-dialog::backdrop {
  background: color-mix(in srgb, var(--ix-canvas) 72%, transparent);
}
</style>
