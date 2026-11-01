<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { PanelRightOpen, X } from "@lucide/vue"
import {
  getSessionPreview,
  getSessionThread,
  previewSessions,
  type SessionFocus,
} from "@/lib/session-preview"
import { safeSessionReturn } from "@/lib/return-to"
import { sessionDriftCount, sessionFailureCount } from "@/lib/session-detail"
import SessionDetailHeader from "@/components/console/session/detail/SessionDetailHeader.vue"
import SessionStatStrip from "@/components/console/session/detail/SessionStatStrip.vue"
import SessionTimeline from "@/components/console/session/detail/SessionTimeline.vue"
import SessionOutline from "@/components/console/session/detail/SessionOutline.vue"
import SessionTurn from "@/components/console/session/detail/SessionTurn.vue"
import SessionTurnsView from "@/components/console/session/detail/SessionTurnsView.vue"
import SessionInspector from "@/components/console/session/detail/SessionInspector.vue"
import SessionShortcuts from "@/components/console/session/detail/SessionShortcuts.vue"
import SessionRawJsonDialog from "@/components/console/session/detail/SessionRawJsonDialog.vue"

const PANELS: SessionFocus[] = ["trace", "memories", "directive", "policy", "drift", "privacy"]
const INSPECTOR_KEY = "ibex.session.inspectorWidth.v2"

const route = useRoute()
const router = useRouter()

const sessionId = computed(() => String(route.params.sessionId ?? ""))
const session = computed(() => getSessionPreview(sessionId.value))
const rounds = computed(() => getSessionThread(session.value))

const listReturn = computed(() => safeSessionReturn(route.query.return))
const memoryReturn = computed(() => route.fullPath)

function initialPanel(): SessionFocus {
  const value = String(route.query.panel ?? "")
  return PANELS.includes(value as SessionFocus) ? (value as SessionFocus) : "trace"
}

function initialTurn(): number {
  const value = Number.parseInt(String(route.query.turn ?? ""), 10)
  if (!Number.isFinite(value)) return 1
  return Math.min(rounds.value.length, Math.max(1, value))
}

const panel = ref<SessionFocus>(initialPanel())
const selectedIndex = ref(initialTurn())
const selectedRound = computed(
  () => rounds.value.find((round) => round.index === selectedIndex.value) ?? rounds.value[0]!,
)
const spanId = ref<string | null>(null)

const view = ref<"conversation" | "turns">("conversation")
const outlineCollapsed = ref(false)
const inspectorCollapsed = ref(false)
const expandAll = ref(false)
const expandKey = ref(0)
const highlightStepId = ref<string | null>(null)
const copiedKey = ref<string | null>(null)
const copiedId = computed(() => copiedKey.value === "session")
const toast = ref<string | null>(null)

const inspectorWidth = ref(460)
const dragging = ref(false)
const narrow = ref(false)

const shortcuts = ref<InstanceType<typeof SessionShortcuts> | null>(null)
const rawJson = ref<InstanceType<typeof SessionRawJsonDialog> | null>(null)
const sheet = ref<HTMLDialogElement | null>(null)
const sheetOpen = ref(false)

const driftCount = computed(() => sessionDriftCount(rounds.value))
const failureCount = computed(() => sessionFailureCount(rounds.value))
const documentTitle = computed(() => `${session.value.title} · Session · IBEX Console`)

const sessionIndex = computed(() => previewSessions.findIndex((entry) => entry.id === sessionId.value))
const prevId = computed(() => (sessionIndex.value > 0 ? previewSessions[sessionIndex.value - 1]!.id : null))
const nextId = computed(() =>
  sessionIndex.value >= 0 && sessionIndex.value < previewSessions.length - 1
    ? previewSessions[sessionIndex.value + 1]!.id
    : null,
)

useHead(() => ({ title: documentTitle.value }))

let clickGuardUntil = 0
let copyTimer: ReturnType<typeof setTimeout> | null = null
let toastTimer: ReturnType<typeof setTimeout> | null = null
let observer: IntersectionObserver | null = null
let resizeStart: { x: number; width: number } | null = null

function isNarrow(): boolean {
  return import.meta.client && window.matchMedia("(max-width: 1279px)").matches
}

function syncViewport(): void {
  narrow.value = isNarrow()
}

function guardClicks(): void {
  clickGuardUntil = Date.now() + 2_000
}

function syncQuery(): void {
  if (!import.meta.client) return
  const nextTurn = String(selectedIndex.value)
  const nextPanel = panel.value
  if (String(route.query.turn ?? "") === nextTurn && String(route.query.panel ?? "") === nextPanel) return
  void router.replace({
    query: {
      ...route.query,
      turn: nextTurn,
      panel: nextPanel,
    },
  })
}

watch([panel, selectedIndex], syncQuery)

watch(
  () => [route.query.turn, route.query.panel],
  () => {
    const nextTurn = Number.parseInt(String(route.query.turn ?? ""), 10)
    if (Number.isFinite(nextTurn)) {
      const clamped = Math.min(rounds.value.length, Math.max(1, nextTurn))
      if (clamped !== selectedIndex.value) {
        selectedIndex.value = clamped
        guardClicks()
        scrollToTurn(clamped, "auto")
      }
    }
    const nextPanel = String(route.query.panel ?? "")
    if (PANELS.includes(nextPanel as SessionFocus) && nextPanel !== panel.value) {
      panel.value = nextPanel as SessionFocus
    }
  },
)

watch(
  () => rounds.value,
  () => {
    if (selectedIndex.value > rounds.value.length) selectedIndex.value = rounds.value.length
  },
)

function scrollToTurn(index: number, behavior: ScrollBehavior = "smooth"): void {
  if (!import.meta.client) return
  void nextTick(() => {
    document.getElementById(`turn-${index}`)?.scrollIntoView({ behavior, block: "start" })
  })
}

function selectTurn(index: number, options: { scroll?: boolean; open?: boolean } = {}): void {
  const next = Math.min(rounds.value.length, Math.max(1, index))
  selectedIndex.value = next
  guardClicks()
  if (options.scroll !== false) scrollToTurn(next)
  if (options.open) openInspector()
}

function stepTurn(delta: number): void {
  selectTurn(selectedIndex.value + delta)
}

function inspect(nextPanel: SessionFocus, nextSpanId: string | null = null): void {
  panel.value = nextPanel
  if (nextSpanId) spanId.value = nextSpanId
  if (isNarrow()) openInspector()
  guardClicks()
}

function openInspector(): void {
  if (!import.meta.client) return
  if (isNarrow()) {
    sheetOpen.value = true
    void nextTick(() => {
      if (!sheet.value?.open) sheet.value?.showModal()
    })
    return
  }
  inspectorCollapsed.value = false
}

function closeSheet(): void {
  sheet.value?.close()
  sheetOpen.value = false
}

function onSheetBackdrop(event: MouseEvent): void {
  if (event.target === sheet.value) closeSheet()
}

function toggleInspector(): void {
  if (isNarrow()) {
    if (sheet.value?.open) closeSheet()
    else openInspector()
    return
  }
  inspectorCollapsed.value = !inspectorCollapsed.value
}

function toggleOutline(): void {
  outlineCollapsed.value = !outlineCollapsed.value
}

function toggleExpandAll(): void {
  expandAll.value = !expandAll.value
  expandKey.value += 1
}

function jumpDrift(): void {
  const flagged = rounds.value.find((round) => round.drift !== null)
  if (!flagged) return
  selectTurn(flagged.index, { open: true })
  panel.value = "drift"
}

function showTranscript(targetSpanId: string | null): void {
  if (targetSpanId) highlightStepId.value = targetSpanId
  const index = selectedIndex.value
  guardClicks()
  if (isNarrow()) closeSheet()
  scrollToTurn(index)
  if (targetSpanId) {
    setTimeout(() => {
      highlightStepId.value = null
    }, 2_600)
  }
}

function copyValue(value: string, label: string): void {
  if (!import.meta.client) return
  const key =
    label === "Session ID"
      ? "session"
      : label === "Trace ID"
        ? `trace-${rounds.value.find((round) => round.traceId === value)?.id ?? value}`
        : value
  void navigator.clipboard
    .writeText(value)
    .then(() => {
      copiedKey.value = key
      toast.value = `${label} copied`
      if (toastTimer) clearTimeout(toastTimer)
      toastTimer = setTimeout(() => {
        toast.value = null
      }, 1_800)
    })
    .catch(() => {
      copiedKey.value = null
    })
  if (copyTimer) clearTimeout(copyTimer)
  copyTimer = setTimeout(() => {
    copiedKey.value = null
  }, 1_500)
}

function onHoverSpan(id: string | null): void {
  highlightStepId.value = id
}

function isTypingTarget(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null
  if (!element) return false
  const tag = element.tagName.toLowerCase()
  return tag === "input" || tag === "textarea" || tag === "select" || element.isContentEditable
}

function onKeydown(event: KeyboardEvent): void {
  if (event.metaKey || event.ctrlKey || event.altKey) return
  if (isTypingTarget(event.target)) return

  const openDialog = document.querySelector("dialog[open]")
  if (openDialog) {
    if (event.key === "?") {
      event.preventDefault()
      shortcuts.value?.toggle()
    }
    return
  }

  const key = event.key
  const lower = key.toLowerCase()

  if (lower === "j") {
    event.preventDefault()
    stepTurn(1)
    return
  }
  if (lower === "k") {
    event.preventDefault()
    stepTurn(-1)
    return
  }
  if (/^[1-6]$/.test(key)) {
    event.preventDefault()
    panel.value = PANELS[Number(key) - 1]!
    if (isNarrow()) openInspector()
    return
  }
  if (key === "?") {
    event.preventDefault()
    shortcuts.value?.toggle()
    return
  }
  if (lower === "e") {
    event.preventDefault()
    toggleExpandAll()
    return
  }
  if (key === "[") {
    event.preventDefault()
    toggleOutline()
    return
  }
  if (key === "]") {
    event.preventDefault()
    toggleInspector()
  }
}

function observeTurns(): void {
  if (!import.meta.client) return
  observer?.disconnect()
  if (view.value !== "conversation") return
  const ratios = new Map<Element, number>()
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) ratios.set(entry.target, entry.isIntersecting ? entry.intersectionRatio : 0)
      if (Date.now() < clickGuardUntil) return
      let best: Element | null = null
      let bestRatio = 0
      for (const [element, ratio] of ratios) {
        if (ratio > bestRatio) {
          best = element
          bestRatio = ratio
        }
      }
      if (!best || bestRatio <= 0) return
      const index = Number((best as HTMLElement).dataset.turnIndex)
      if (Number.isFinite(index) && index !== selectedIndex.value) selectedIndex.value = index
    },
    { rootMargin: "-28% 0px -55% 0px", threshold: [0, 0.2, 0.4, 0.6, 0.8, 1] },
  )
  document.querySelectorAll<HTMLElement>("[data-turn-index]").forEach((element) => observer?.observe(element))
}

watch(view, () => {
  void nextTick(observeTurns)
})

watch(
  () => rounds.value.map((round) => round.id).join(","),
  () => {
    void nextTick(observeTurns)
  },
)

function readWidth(): void {
  if (!import.meta.client) return
  const stored = Number.parseInt(window.localStorage.getItem(INSPECTOR_KEY) ?? "", 10)
  if (Number.isFinite(stored)) inspectorWidth.value = Math.min(560, Math.max(360, stored))
}

function startResize(event: PointerEvent): void {
  if (isNarrow()) return
  dragging.value = true
  resizeStart = { x: event.clientX, width: inspectorWidth.value }
  window.addEventListener("pointermove", onResizeMove)
  window.addEventListener("pointerup", stopResize)
  event.preventDefault()
}

function onResizeMove(event: PointerEvent): void {
  if (!resizeStart) return
  const next = resizeStart.width - (event.clientX - resizeStart.x)
  inspectorWidth.value = Math.min(560, Math.max(360, next))
}

function stopResize(): void {
  dragging.value = false
  resizeStart = null
  window.removeEventListener("pointermove", onResizeMove)
  window.removeEventListener("pointerup", stopResize)
  if (import.meta.client) window.localStorage.setItem(INSPECTOR_KEY, String(inspectorWidth.value))
}

onMounted(() => {
  window.addEventListener("keydown", onKeydown)
  window.addEventListener("resize", syncViewport)
  syncViewport()
  readWidth()
  void nextTick(() => {
    observeTurns()
    if (selectedIndex.value > 1) {
      guardClicks()
      scrollToTurn(selectedIndex.value, "auto")
    }
  })
})

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKeydown)
  window.removeEventListener("resize", syncViewport)
  window.removeEventListener("pointermove", onResizeMove)
  window.removeEventListener("pointerup", stopResize)
  observer?.disconnect()
  if (copyTimer) clearTimeout(copyTimer)
  if (toastTimer) clearTimeout(toastTimer)
})
</script>

<template>
  <div class="flex w-full flex-col gap-2" :style="{ '--ix-inspector-w': `${inspectorWidth}px` }">
    <SessionDetailHeader
      :session="session"
      :return-to="listReturn"
      :prev-id="prevId"
      :next-id="nextId"
      :drift-count="driftCount"
      :failure-count="failureCount"
      :copied-id="copiedId"
      @copy="copyValue"
      @show-raw-json="rawJson?.open()"
      @jump-drift="jumpDrift"
    />

    <SessionStatStrip :session="session" :rounds="rounds" />

    <SessionTimeline
      :session="session"
      :rounds="rounds"
      :selected-index="selectedIndex"
      @select="selectTurn($event, { scroll: true })"
    />

    <div
      class="ix-layout"
      :class="inspectorCollapsed && 'ix-layout-inspector-collapsed'"
    >
      <SessionOutline
        :session="session"
        :rounds="rounds"
        :selected-index="selectedIndex"
        :view="view"
        :collapsed="outlineCollapsed"
        @select="selectTurn($event, { scroll: true })"
        @update:view="view = $event"
        @update:collapsed="outlineCollapsed = $event"
      />

      <section class="ix-transcript-column min-w-0" aria-label="Conversation transcript">
        <template v-if="view === 'conversation'">
          <template v-for="(round, index) in rounds" :key="round.id">
            <div v-if="index > 0" class="ix-turn-divider" aria-hidden="true">
              <span>Turn {{ round.index }}</span>
            </div>
            <SessionTurn
              :session="session"
              :round="round"
              :selected="selectedIndex === round.index"
              :expand-all="expandAll"
              :expand-key="expandKey"
              :highlight-step-id="highlightStepId"
              :return-to="memoryReturn"
              :copied-key="copiedKey"
              @select="selectTurn($event, { scroll: false })"
              @inspect="inspect"
              @copy="copyValue"
            />
          </template>
        </template>

        <SessionTurnsView
          v-else
          :session="session"
          :rounds="rounds"
          :selected-index="selectedIndex"
          @select="
            selectTurn($event, { scroll: true });
            view = 'conversation'
          "
        />
      </section>

      <div class="ix-inspector-column" :class="inspectorCollapsed && 'ix-inspector-column-hidden'">
        <button
          type="button"
          class="ix-resize-handle"
          :class="dragging && 'ix-resize-handle-active'"
          aria-label="Resize inspector"
          title="Drag to resize the inspector"
          @pointerdown="startResize"
        />
        <SessionInspector
          id-prefix="side"
          :session="session"
          :rounds="rounds"
          :round="selectedRound"
          :panel="panel"
          :span-id="spanId"
          :return-to="memoryReturn"
          @update:panel="panel = $event"
          @update:span-id="spanId = $event"
          @select-turn="selectTurn($event, { scroll: true })"
          @step-turn="stepTurn"
          @transcript="showTranscript"
          @copy="copyValue"
          @hover="onHoverSpan"
          @expand="openInspector"
        />
      </div>
    </div>

    <button
      v-if="narrow || inspectorCollapsed"
      type="button"
      class="ix-inspect-fab"
      @click="openInspector"
    >
      <PanelRightOpen :size="15" :stroke-width="1.75" aria-hidden="true" />
      Inspect
    </button>

    <dialog ref="sheet" class="ix-sheet" aria-label="Turn inspector" @click="onSheetBackdrop" @close="sheetOpen = false">
      <div class="ix-sheet-stack">
        <div class="ix-sheet-bar">
          <p class="text-xs font-medium text-fg-2">Turn inspector</p>
          <button
            type="button"
            class="ix-sheet-close"
            aria-label="Close inspector"
            @click="closeSheet"
          >
            <X :size="15" :stroke-width="1.75" aria-hidden="true" />
          </button>
        </div>
        <div v-if="sheetOpen" class="ix-sheet-inspector">
          <SessionInspector
            id-prefix="sheet"
            :session="session"
            :rounds="rounds"
            :round="selectedRound"
            :panel="panel"
            :span-id="spanId"
            :return-to="memoryReturn"
            @update:panel="panel = $event"
            @update:span-id="spanId = $event"
            @select-turn="selectTurn($event, { scroll: true })"
            @step-turn="stepTurn"
            @transcript="showTranscript"
            @copy="copyValue"
            @hover="onHoverSpan"
            @expand="openInspector"
          />
        </div>
      </div>
    </dialog>

    <SessionShortcuts ref="shortcuts" />
    <SessionRawJsonDialog ref="rawJson" :session="session" :rounds="rounds" />

    <Transition name="ix-toast">
      <p v-if="toast" class="ix-toast" role="status" aria-live="polite">{{ toast }}</p>
    </Transition>
  </div>
</template>

<style scoped>
.ix-layout {
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr) var(--ix-inspector-w, 420px);
  justify-content: space-between;
  align-items: start;
  gap: 1.25rem;
}

.ix-layout-inspector-collapsed {
  grid-template-columns: 248px minmax(0, 1fr);
}

.ix-transcript-column {
  position: relative;
  width: 100%;
  max-width: 760px;
  justify-self: center;
  padding-bottom: 2rem;
}

.ix-turn-divider {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0.375rem 0 0.125rem;
  padding-left: 3.25rem;
  font-size: 0.6875rem;
  line-height: 1.25rem;
  font-weight: 500;
  color: var(--ix-fg-3);
}

.ix-turn-divider::after {
  content: "";
  height: 1px;
  flex: 1;
  background: var(--ix-line-subtle);
}

.ix-inspector-column {
  position: sticky;
  top: calc(3rem + 1rem);
  height: calc(100dvh - 5rem);
  min-height: 24rem;
}

.ix-inspector-column-hidden {
  display: none;
}

.ix-resize-handle {
  position: absolute;
  top: 50%;
  left: -0.4375rem;
  z-index: 5;
  width: 0.5rem;
  height: 3.5rem;
  transform: translateY(-50%);
  border-radius: 9999px;
  background: transparent;
  cursor: col-resize;
  transition: background-color 120ms;
}

.ix-resize-handle::after {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0.1875rem;
  width: 2px;
  border-radius: 9999px;
  background: var(--ix-line-subtle);
  transition: background-color 120ms;
}

.ix-resize-handle:hover::after,
.ix-resize-handle-active::after {
  background: var(--ix-accent-memory);
}

.ix-resize-handle:focus-visible {
  outline: 2px solid var(--ix-accent-memory);
  outline-offset: 2px;
}

.ix-inspect-fab {
  position: fixed;
  right: 1rem;
  bottom: 1rem;
  z-index: 30;
  display: inline-flex;
  height: 2.25rem;
  align-items: center;
  gap: 0.375rem;
  border: 1px solid var(--ix-line);
  border-radius: 9999px;
  background: var(--ix-overlay);
  padding: 0 0.75rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--ix-fg-1);
  box-shadow: 0 6px 20px rgb(0 0 0 / 0.35);
  transition: border-color 120ms;
}

.ix-inspect-fab:hover {
  border-color: var(--ix-line-strong);
}

.ix-inspect-fab:focus-visible {
  outline: 2px solid var(--ix-accent-memory);
  outline-offset: 2px;
}

.ix-sheet {
  width: min(44rem, calc(100vw - 2rem));
  max-width: none;
  height: calc(100dvh - 2rem);
  max-height: none;
  margin: auto;
  border: 0;
  border-radius: 12px;
  background: transparent;
  padding: 0;
  color: var(--ix-fg-1);
  overflow: visible;
}

.ix-sheet::backdrop {
  background: rgb(0 0 0 / 0.55);
}

.ix-sheet-stack {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  border: 1px solid var(--ix-line);
  border-radius: 12px;
  background: var(--ix-surface);
  overflow: hidden;
}

.ix-sheet-bar {
  display: flex;
  flex: none;
  height: 2.5rem;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  border-bottom: 1px solid var(--ix-line-subtle);
  padding: 0 0.5rem 0 0.75rem;
}

.ix-sheet-close {
  display: inline-flex;
  width: 1.75rem;
  height: 1.75rem;
  align-items: center;
  justify-content: center;
  border-radius: 5px;
  color: var(--ix-fg-3);
  transition: background-color 120ms, color 120ms;
}

.ix-sheet-close:hover {
  background: var(--ix-raised);
  color: var(--ix-fg-1);
}

.ix-sheet-inspector {
  min-height: 0;
  flex: 1 1 auto;
}

.ix-toast {
  position: fixed;
  bottom: 1.25rem;
  left: 50%;
  z-index: 60;
  transform: translateX(-50%);
  border: 1px solid var(--ix-line);
  border-radius: 9999px;
  background: var(--ix-overlay);
  padding: 0.375rem 0.75rem;
  font-size: 0.75rem;
  line-height: 1rem;
  color: var(--ix-fg-1);
  box-shadow: 0 6px 24px rgb(0 0 0 / 0.35);
}

.ix-toast-enter-active,
.ix-toast-leave-active {
  transition: opacity 150ms ease-out, transform 150ms ease-out;
}

.ix-toast-enter-from,
.ix-toast-leave-to {
  opacity: 0;
  transform: translate(-50%, 4px);
}

@media (min-width: 1280px) and (max-width: 1439px) {
  .ix-layout {
    grid-template-columns: 56px minmax(0, 1fr) var(--ix-inspector-w, 400px);
    gap: 1rem;
  }

  .ix-layout-inspector-collapsed {
    grid-template-columns: 56px minmax(0, 1fr);
  }
}

@media (max-width: 1279px) {
  .ix-layout {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }

  .ix-layout-inspector-collapsed {
    grid-template-columns: minmax(0, 1fr);
  }

  .ix-inspector-column {
    display: none;
  }

  .ix-sheet {
    width: min(32rem, calc(100vw - 1rem));
    height: calc(100dvh - 1rem);
  }
}

@media (max-width: 767px) {
  .ix-sheet {
    width: 100vw;
    height: 100dvh;
    border-radius: 0;
  }

  .ix-sheet-stack {
    border: 0;
    border-radius: 0;
  }

  .ix-turn-divider {
    padding-left: 2.5rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ix-toast-enter-active,
  .ix-toast-leave-active,
  .ix-inspect-fab,
  .ix-resize-handle::after {
    transition-duration: 1ms;
  }
}
</style>
