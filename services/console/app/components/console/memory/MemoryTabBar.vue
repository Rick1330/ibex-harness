<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import type { MemoryDetail } from "@/lib/memory-detail-preview"

const props = defineProps<{
  detail: MemoryDetail
  view: string
  showCondensed: boolean
}>()

const emit = defineEmits<{ select: [id: "overview" | "evidence" | "usage" | "history"] }>()

const VIEWS = [
  { id: "overview", label: "Overview" },
  { id: "evidence", label: "Evidence" },
  { id: "usage", label: "Usage" },
  { id: "history", label: "History" },
] as const

type ViewId = (typeof VIEWS)[number]["id"]

const counts = computed<Record<ViewId, number | null>>(() => ({
  overview: null,
  evidence: props.detail.evaluation.checks.length,
  usage: props.detail.retrieval.count,
  history: props.detail.versions.length,
}))

const tablist = ref<HTMLElement | null>(null)
const indicator = ref({ left: 0, width: 0, ready: false })

function moveIndicator(): void {
  const root = tablist.value
  if (!root) return
  const active = root.querySelector<HTMLButtonElement>(`[data-memory-tab="${props.view}"]`)
  if (!active) return
  indicator.value = { left: active.offsetLeft, width: active.offsetWidth, ready: true }
}

watch(
  () => [props.view, props.detail.memory.id],
  () => {
    void nextTick(moveIndicator)
  },
  { immediate: true },
)

let resizeObserver: ResizeObserver | null = null
onMounted(() => {
  void nextTick(moveIndicator)
  if (typeof ResizeObserver !== "undefined" && tablist.value) {
    resizeObserver = new ResizeObserver(() => moveIndicator())
    resizeObserver.observe(tablist.value)
  }
})
onBeforeUnmount(() => resizeObserver?.disconnect())

function onKeydown(event: KeyboardEvent): void {
  const last = VIEWS.length - 1
  const index = VIEWS.findIndex((entry) => entry.id === props.view)
  let next = index
  if (event.key === "ArrowRight") next = index === last ? 0 : index + 1
  else if (event.key === "ArrowLeft") next = index === 0 ? last : index - 1
  else if (event.key === "Home") next = 0
  else if (event.key === "End") next = last
  else return
  event.preventDefault()
  emit("select", VIEWS[next]!.id)
  void nextTick(() => {
    tablist.value?.querySelector<HTMLButtonElement>(`[data-memory-tab="${VIEWS[next]!.id}"]`)?.focus()
  })
}
</script>

<template>
  <div class="sticky top-12 z-20 -mx-4 border-b border-line-subtle bg-canvas/85 backdrop-blur-sm sm:-mx-5 lg:-mx-6">
    <div class="mx-auto flex h-11 max-w-[90rem] items-center gap-3 px-4 sm:px-5 lg:px-6">
      <div
        v-show="showCondensed"
        class="flex min-w-0 shrink-0 items-center gap-2 fade-in-0 animate-in duration-200 max-lg:hidden"
      >
        <span class="max-w-[24ch] truncate text-xs font-medium text-fg-2">{{ detail.title }}</span>
        <span class="inline-flex shrink-0 items-center gap-1 text-xs text-fg-3">
          <span
            class="size-1.5 rounded-full bg-current"
            :class="{
              'text-ok': detail.memory.status === 'active',
              'text-warn': detail.memory.status === 'quarantined',
              'text-crit': detail.memory.status === 'deleted',
            }"
            aria-hidden="true"
          />
          {{ detail.memory.status === "active" ? "Active" : "Retired" }}
        </span>
        <span class="h-4 w-px bg-line-subtle" aria-hidden="true" />
      </div>

      <div
        ref="tablist"
        class="ix-tabs min-w-0 flex-1"
        role="tablist"
        aria-label="Memory record views"
        @keydown="onKeydown"
      >
        <button
          v-for="item in VIEWS"
          :id="`memory-view-tab-${item.id}`"
          :key="item.id"
          type="button"
          role="tab"
          class="ix-tab"
          :class="view === item.id && 'ix-tab-active'"
          :data-memory-tab="item.id"
          :aria-selected="view === item.id"
          :aria-controls="`memory-view-panel-${item.id}`"
          :tabindex="view === item.id ? 0 : -1"
          @click="emit('select', item.id)"
        >
          {{ item.label }}
          <span v-if="counts[item.id] !== null" class="ix-tab-count">{{ counts[item.id] }}</span>
        </button>
        <span
          class="ix-tab-indicator"
          :class="indicator.ready && 'ix-tab-indicator-ready'"
          :style="{ transform: `translateX(${indicator.left}px)`, width: `${indicator.width}px` }"
          aria-hidden="true"
        />
      </div>


    </div>
  </div>
</template>

<style scoped>
.ix-tabs {
  position: relative;
  display: flex;
  gap: 0.25rem;
  overflow-x: auto;
  scrollbar-width: none;
}

.ix-tabs::-webkit-scrollbar {
  display: none;
}

.ix-tab {
  display: inline-flex;
  height: 2.25rem;
  flex: none;
  align-items: center;
  gap: 0.375rem;
  border-radius: 6px;
  padding: 0 0.625rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--ix-fg-3);
  transition: color 120ms, background-color 120ms;
}

.ix-tab:hover {
  background: var(--ix-raised);
  color: var(--ix-fg-1);
}

.ix-tab:focus-visible {
  outline: 2px solid var(--ix-accent);
  outline-offset: -2px;
}

.ix-tab-active {
  color: var(--ix-fg-1);
}

.ix-tab-count {
  display: inline-flex;
  min-width: 1.125rem;
  height: 1.125rem;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  padding: 0 0.25rem;
  background: var(--ix-raised);
  font-family: var(--font-mono);
  font-size: 0.625rem;
  font-variant-numeric: tabular-nums;
  color: var(--ix-fg-3);
}

.ix-tab-active .ix-tab-count {
  background: var(--ix-memory-tint);
  color: var(--ix-memory);
}

.ix-tab-indicator {
  position: absolute;
  bottom: 0;
  left: 0;
  height: 2px;
  border-radius: 2px;
  background: var(--ix-memory);
}

.ix-tab-indicator-ready {
  transition: transform 200ms ease-out, width 200ms ease-out;
}

@media (max-width: 767px) {
  .ix-tabs {
    overflow-x: visible;
  }
}

</style>
