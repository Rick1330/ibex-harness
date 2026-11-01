<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import type { MemoryView } from "@/lib/memory-list-query"

const props = defineProps<{
  view: MemoryView
  counts: Record<MemoryView, number>
  modified: boolean
}>()

const emit = defineEmits<{ select: [view: MemoryView] }>()

const views: Array<{ key: MemoryView; label: string }> = [
  { key: "all", label: "All" },
  { key: "review", label: "Needs review" },
  { key: "conflicts", label: "Conflicts" },
  { key: "pinned", label: "Pinned" },
  { key: "never", label: "Never retrieved" },
  { key: "expiring", label: "Expiring" },
  { key: "tombstoned", label: "Tombstoned" },
]

const tablist = ref<HTMLElement | null>(null)
const indicator = ref({ left: 0, width: 0, ready: false })
let observer: ResizeObserver | null = null

function moveIndicator(): void {
  const root = tablist.value
  if (!root) return
  const active = root.querySelector<HTMLButtonElement>(`[data-memory-view="${props.view}"]`)
  if (!active) return
  indicator.value = { left: active.offsetLeft, width: active.offsetWidth, ready: true }
}

watch(
  () => props.view,
  () => {
    void nextTick(moveIndicator)
  },
)

onMounted(() => {
  void nextTick(moveIndicator)
  if (typeof ResizeObserver !== "undefined" && tablist.value) {
    observer = new ResizeObserver(moveIndicator)
    observer.observe(tablist.value)
  }
})
onBeforeUnmount(() => observer?.disconnect())

function onKeydown(event: KeyboardEvent): void {
  const current = views.findIndex((entry) => entry.key === props.view)
  let next = current
  if (current < 0) next = 0
  else if (event.key === "ArrowRight") next = current === views.length - 1 ? 0 : current + 1
  else if (event.key === "ArrowLeft") next = current === 0 ? views.length - 1 : current - 1
  else if (event.key === "Home") next = 0
  else if (event.key === "End") next = views.length - 1
  else return
  event.preventDefault()
  const target = views[next]!
  emit("select", target.key)
  void nextTick(() => {
    tablist.value?.querySelector<HTMLButtonElement>(`[data-memory-view="${target.key}"]`)?.focus()
  })
}
</script>

<template>
  <div
    ref="tablist"
    class="ix-scroll relative -mb-px flex min-w-0 items-stretch gap-1 overflow-x-auto"
    role="tablist"
    aria-label="Saved memory views"
    @keydown="onKeydown"
  >
    <button
      v-for="entry in views"
      :id="`memory-list-view-${entry.key}`"
      :key="entry.key"
      type="button"
      role="tab"
      class="relative inline-flex h-8 shrink-0 items-center gap-1.5 rounded-t-md px-2.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-accent-memory"
      :class="view === entry.key ? 'text-fg-1' : 'text-fg-3 hover:bg-surface-2 hover:text-fg-2'"
      :data-memory-view="entry.key"
      :aria-selected="view === entry.key"
      :tabindex="view === entry.key ? 0 : -1"
      @click="emit('select', entry.key)"
    >
      <span class="whitespace-nowrap">{{ entry.label }}</span>
      <span
        class="inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1 font-mono text-[0.625rem] leading-none tabular-nums"
        :class="view === entry.key ? 'bg-memory-tint text-fg-1' : 'bg-surface-2 text-fg-3'"
      >
        {{ counts[entry.key] }}
      </span>
      <span
        v-if="view === entry.key && modified"
        class="size-1.5 rounded-full bg-warn"
        role="img"
        aria-label="Filters differ from this saved view"
        title="Filters differ from this saved view. Click the view to reset them."
      />
    </button>
    <span
      class="pointer-events-none bottom-0 h-0.5 rounded-full bg-accent-memory"
      :class="indicator.ready && 'transition-[transform,width] duration-200 ease-out'"
      :style="{ position: 'absolute', transform: `translateX(${indicator.left}px)`, width: `${indicator.width}px`, left: 0 }"
      aria-hidden="true"
    />
  </div>
</template>
