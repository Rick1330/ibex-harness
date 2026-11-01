<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { ArrowLeft, ShieldAlert } from "@lucide/vue"
import { previewMemories } from "@/lib/memory-preview"
import type { MemoryDetail } from "@/lib/memory-detail-preview"
import MemoryDetailHeader from "./MemoryDetailHeader.vue"
import MemoryTabBar from "./MemoryTabBar.vue"
import MemoryEvidencePanel from "./MemoryEvidencePanel.vue"
import MemoryHistoryPanel from "./MemoryHistoryPanel.vue"
import MemoryOverviewPanel from "./MemoryOverviewPanel.vue"
import MemoryUsagePanel from "./MemoryUsagePanel.vue"

const props = defineProps<{
  detail: MemoryDetail | null
  memoryId: string
  returnTo: string
}>()

const VIEWS = ["overview", "evidence", "usage", "history"] as const
type MemoryViewId = (typeof VIEWS)[number]

function resolveView(value: unknown): MemoryViewId {
  return typeof value === "string" && (VIEWS as readonly string[]).includes(value) ? (value as MemoryViewId) : "overview"
}

const route = useRoute()
const router = useRouter()
const view = ref<MemoryViewId>(resolveView(route.query.view))

watch(
  () => route.query.view,
  (value) => {
    view.value = resolveView(value)
  },
)

function selectView(next: MemoryViewId, focus = false): void {
  view.value = next
  const query = { ...route.query }
  if (next === "overview") delete query.view
  else query.view = next
  void router.replace({ query })
  if (focus) {
    document.getElementById(`memory-view-tab-${next}`)?.focus()
  }
}

// Prev/next step through the full preview memory order, preserving the return target.
const currentIndex = computed(() => previewMemories.findIndex((memory) => memory.id === props.memoryId))
const prevTarget = computed(() =>
  currentIndex.value > 0 ? previewMemories[currentIndex.value - 1]!.id : null,
)
const nextTarget = computed(() =>
  currentIndex.value >= 0 && currentIndex.value < previewMemories.length - 1
    ? previewMemories[currentIndex.value + 1]!.id
    : null,
)

function navigateToMemory(id: string): void {
  void router.push({ path: `/memories/${id}`, query: route.query.return ? { return: route.query.return } : {} })
}

function isTypingTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && Boolean(target.closest("input, textarea, select, [contenteditable]"))
}

function onGlobalKeydown(event: KeyboardEvent): void {
  if (event.metaKey || event.ctrlKey || event.altKey) return
  if (isTypingTarget(event.target)) return
  if (event.key === "j" && nextTarget.value) {
    event.preventDefault()
    navigateToMemory(nextTarget.value)
  } else if (event.key === "k" && prevTarget.value) {
    event.preventDefault()
    navigateToMemory(prevTarget.value)
  } else if (["1", "2", "3", "4"].includes(event.key)) {
    event.preventDefault()
    selectView(VIEWS[Number(event.key) - 1]!, true)
  }
}

// Condensed header fades into the sticky tab bar once the page header scrolls out.
const headerEl = ref<HTMLElement | null>(null)
const showCondensed = ref(false)
let observer: IntersectionObserver | null = null

onMounted(() => {
  window.addEventListener("keydown", onGlobalKeydown)
  if (headerEl.value && typeof IntersectionObserver !== "undefined") {
    observer = new IntersectionObserver(
      ([entry]) => {
        showCondensed.value = !(entry?.isIntersecting ?? true)
      },
      { rootMargin: "-48px 0px 0px 0px" },
    )
    observer.observe(headerEl.value)
  }
})
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onGlobalKeydown)
  observer?.disconnect()
})

const backLabel = computed(() => (props.returnTo.startsWith("/sessions/") ? "Back to session" : "Back to memories"))
</script>

<template>
  <div class="mx-auto flex w-full max-w-[90rem] min-w-0 flex-1 flex-col pb-2">
    <template v-if="detail">
      <div ref="headerEl">
        <MemoryDetailHeader
          :detail="detail"
          :memory-id="memoryId"
          :return-to="returnTo"
          :prev-target="prevTarget"
          :next-target="nextTarget"
          @navigate="navigateToMemory"
          @show-raw-json="selectView('overview')"
        />
      </div>

      <div class="mt-6">
        <MemoryTabBar :detail="detail" :view="view" :show-condensed="showCondensed" @select="selectView($event)" />
      </div>

      <div class="mt-6 min-w-0">
        <Transition name="memory-panel" mode="out-in">
          <div
            :id="`memory-view-panel-${view}`"
            :key="view"
            role="tabpanel"
            :aria-labelledby="`memory-view-tab-${view}`"
            class="min-w-0 rounded focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent"
          >
            <MemoryOverviewPanel
              v-if="view === 'overview'"
              :detail="detail"
              :return-to="returnTo"
              @view="selectView($event)"
            />
            <MemoryEvidencePanel v-else-if="view === 'evidence'" :detail="detail" :return-to="returnTo" />
            <MemoryUsagePanel v-else-if="view === 'usage'" :detail="detail" />
            <MemoryHistoryPanel v-else :detail="detail" />
          </div>
        </Transition>
      </div>
    </template>

    <template v-else>
      <div class="flex flex-wrap items-center justify-between gap-3">
        <NuxtLink :to="returnTo" class="inline-flex items-center gap-1.5 text-xs text-fg-3 transition-colors hover:text-fg-1">
          <ArrowLeft :size="13" :stroke-width="1.75" aria-hidden="true" />
          {{ backLabel }}
        </NuxtLink>
        <div class="flex items-center gap-1.5">
          <IxStatusBadge status="preview" label="Preview" />
        </div>
      </div>

      <section class="ix-preview-empty mt-4 rounded-lg border border-line-subtle bg-surface" aria-label="Unknown memory">
        <span class="flex size-10 items-center justify-center rounded-full border border-line-subtle bg-raised text-fg-3">
          <ShieldAlert :size="18" :stroke-width="1.75" aria-hidden="true" />
        </span>
        <p class="text-sm font-medium text-fg-1">Unknown or out-of-org memory</p>
        <p class="max-w-md text-[0.8125rem] leading-6 text-fg-3 text-pretty">
          “{{ memoryId }}” is not in the illustrative fixture set. A live read must return an empty or 404 result without leaking existence.
        </p>
        <NuxtLink :to="returnTo" class="ix-button-secondary mt-1 h-9 px-3.5 text-[0.8125rem]">Return to memories</NuxtLink>
      </section>
    </template>
  </div>
</template>

<style scoped>
.memory-panel-enter-active {
  transition: opacity 160ms ease, transform 160ms ease;
}

.memory-panel-leave-active {
  transition: opacity 100ms ease;
}

.memory-panel-enter-from {
  opacity: 0;
  transform: translateY(4px);
}

.memory-panel-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .memory-panel-enter-active,
  .memory-panel-leave-active {
    transition: none;
  }
}
</style>
