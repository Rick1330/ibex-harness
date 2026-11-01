<script setup lang="ts">
import { computed, ref } from "vue"
import { Circle, MessageSquare, TriangleAlert } from "@lucide/vue"
import type { PreviewSession, SessionRound } from "@/lib/session-preview"
import { memoryUsage, outcomeTone, toolUsage } from "@/lib/session-detail"

type Filter = { type: "tool"; key: string } | { type: "memory"; key: string } | null

const props = defineProps<{
  session: PreviewSession
  rounds: SessionRound[]
  selectedIndex: number
  view: "conversation" | "turns"
  collapsed: boolean
}>()

const emit = defineEmits<{
  select: [index: number]
  "update:view": [view: "conversation" | "turns"]
  "update:collapsed": [collapsed: boolean]
}>()

const filter = ref<Filter>(null)

const tools = computed(() => toolUsage(props.rounds))
const memories = computed(() => memoryUsage(props.rounds).slice(0, 4))

const filteredTurns = computed(() => {
  if (!filter.value) return null
  const entry =
    filter.value.type === "tool"
      ? tools.value.find((item) => item.name === filter.value?.key)
      : memories.value.find((item) => item.id === filter.value?.key)
  return new Set(entry?.turns ?? [])
})

function snippet(round: SessionRound): string {
  const text = round.userText.trim()
  return text.length > 32 ? `${text.slice(0, 31).trimEnd()}…` : text
}

function toggleFilter(next: Filter): void {
  filter.value = filter.value?.type === next?.type && filter.value?.key === next?.key ? null : next
}

function isDimmed(index: number): boolean {
  return filteredTurns.value !== null && !filteredTurns.value.has(index)
}

function isHighlighted(index: number): boolean {
  return filteredTurns.value !== null && filteredTurns.value.has(index)
}

function dotClass(round: SessionRound): string {
  const tone = outcomeTone(round.outcome)
  return tone === "destructive" ? "text-crit" : tone === "warning" ? "text-warn" : "text-ok"
}
</script>

<template>
  <nav class="ix-outline" aria-label="Turns">
    <!-- Full outline -->
    <div class="ix-outline-full" :class="collapsed && 'ix-outline-full-collapsed'">
      <div class="ix-outline-head">
        <p class="text-[0.625rem] leading-4 font-semibold tracking-[0.1em] text-fg-3 uppercase">Turns</p>
        <span class="ml-auto inline-flex items-center gap-0.5 text-[0.625rem] leading-4 text-fg-3">
          <kbd class="ix-kbd">J</kbd><kbd class="ix-kbd">K</kbd>
        </span>
      </div>

      <div class="ix-toggle" role="group" aria-label="Transcript view">
        <button
          type="button"
          class="ix-toggle-button"
          :class="view === 'conversation' && 'ix-toggle-button-active'"
          :aria-pressed="view === 'conversation'"
          @click="emit('update:view', 'conversation')"
        >
          Conversation
        </button>
        <button
          type="button"
          class="ix-toggle-button"
          :class="view === 'turns' && 'ix-toggle-button-active'"
          :aria-pressed="view === 'turns'"
          @click="emit('update:view', 'turns')"
        >
          Turns
        </button>
      </div>

      <ol class="mt-2 space-y-0.5">
        <li v-for="round in rounds" :key="round.id">
          <button
            type="button"
            class="ix-outline-row"
            :class="[
              selectedIndex === round.index && 'ix-outline-row-active',
              isDimmed(round.index) && 'ix-outline-row-dim',
              isHighlighted(round.index) && 'ix-outline-row-highlight',
            ]"
            :aria-current="selectedIndex === round.index ? 'true' : undefined"
            @click="emit('select', round.index)"
          >
            <span class="ix-outline-dot" :class="dotClass(round)" aria-hidden="true">
              <TriangleAlert v-if="round.drift" :size="9" :stroke-width="2.2" />
              <Circle v-else :size="7" :stroke-width="3" fill="currentColor" />
            </span>
            <span class="ix-outline-num font-mono">{{ round.index }}</span>
            <span class="min-w-0 flex-1">
              <span class="block truncate text-[0.75rem] leading-4 text-fg-2">{{ snippet(round) }}</span>
              <span class="mt-0.5 flex items-center gap-1.5 text-[0.625rem] leading-3.5 text-fg-3">
                <span class="font-mono tabular-nums">{{ round.latencyMs }} ms</span>
                <span aria-hidden="true">·</span>
                <span>{{ round.toolCalls.length }} {{ round.toolCalls.length === 1 ? "tool" : "tools" }}</span>
                <span v-if="round.drift" class="text-warn">drift</span>
              </span>
            </span>
          </button>
        </li>
      </ol>

      <div class="ix-outline-section">
        <p class="ix-outline-label">Tools used</p>
        <ul class="space-y-0.5">
          <li v-for="tool in tools" :key="tool.name">
            <button
              type="button"
              class="ix-filter-row"
              :class="filter?.type === 'tool' && filter.key === tool.name && 'ix-filter-row-active'"
              :aria-pressed="filter?.type === 'tool' && filter.key === tool.name"
              @click="toggleFilter({ type: 'tool', key: tool.name })"
            >
              <span class="min-w-0 truncate font-mono">{{ tool.name }}</span>
              <span class="ml-auto shrink-0 font-mono text-fg-3 tabular-nums">×{{ tool.count }}</span>
            </button>
          </li>
        </ul>
      </div>

      <div class="ix-outline-section">
        <p class="ix-outline-label">Memories retrieved</p>
        <ul class="space-y-0.5">
          <li v-for="memory in memories" :key="memory.id">
            <button
              type="button"
              class="ix-filter-row"
              :class="filter?.type === 'memory' && filter.key === memory.id && 'ix-filter-row-active'"
              :aria-pressed="filter?.type === 'memory' && filter.key === memory.id"
              @click="toggleFilter({ type: 'memory', key: memory.id })"
            >
              <span class="min-w-0 truncate">{{ memory.label }}</span>
              <span class="ml-auto shrink-0 font-mono text-fg-3 tabular-nums">×{{ memory.count }}</span>
            </button>
          </li>
        </ul>
      </div>

      <p v-if="filter" class="mt-2 text-[0.625rem] leading-4 text-fg-3">
        Highlighting {{ filteredTurns?.size ?? 0 }} {{ filteredTurns?.size === 1 ? "turn" : "turns" }}.
        <button type="button" class="underline underline-offset-2 hover:text-fg-1" @click="filter = null">Clear</button>
      </p>
    </div>

    <!-- 56px rail used from 1280–1439px and when the outline is collapsed -->
    <div class="ix-outline-rail">
      <span class="ix-rail-cap" aria-hidden="true"><MessageSquare :size="13" :stroke-width="1.75" /></span>
      <button
        v-for="round in rounds"
        :key="`rail-${round.id}`"
        type="button"
        class="ix-rail-dot"
        :class="[dotClass(round), selectedIndex === round.index && 'ix-rail-dot-active', isDimmed(round.index) && 'ix-rail-dot-dim']"
        :aria-label="`Turn ${round.index}: ${snippet(round)}`"
        :aria-current="selectedIndex === round.index ? 'true' : undefined"
        :title="`Turn ${round.index} · ${round.latencyMs} ms${round.drift ? ' · drift advisory' : ''}`"
        @click="emit('select', round.index)"
      >
        <span class="font-mono text-[0.625rem] leading-none tabular-nums">{{ round.index }}</span>
      </button>
    </div>
  </nav>
</template>

<style scoped>
.ix-outline {
  min-width: 0;
  /* Let the nav fill the grid row so the inner column can actually stick. */
  align-self: stretch;
}

.ix-outline-full {
  position: sticky;
  top: calc(3rem + 1rem);
  max-height: calc(100dvh - 7rem);
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-right: 0.25rem;
}

.ix-outline-head {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.ix-kbd {
  display: inline-flex;
  min-width: 1rem;
  height: 1rem;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--ix-line-subtle);
  border-radius: 3px;
  background: var(--ix-surface);
  padding: 0 0.1875rem;
  font-family: var(--font-mono);
  font-size: 0.5625rem;
  line-height: 1;
  color: var(--ix-fg-3);
}

.ix-toggle {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2px;
  margin-top: 0.5rem;
  border-radius: 7px;
  background: var(--ix-raised);
  padding: 2px;
}

.ix-toggle-button {
  height: 1.5rem;
  border-radius: 5px;
  font-size: 0.6875rem;
  line-height: 1;
  font-weight: 500;
  color: var(--ix-fg-3);
  transition: background-color 120ms, color 120ms;
}

.ix-toggle-button:hover {
  color: var(--ix-fg-1);
}

.ix-toggle-button-active {
  background: var(--ix-surface);
  color: var(--ix-fg-1);
  box-shadow: 0 1px 2px rgb(0 0 0 / 0.18);
}

.ix-toggle-button:focus-visible,
.ix-outline-row:focus-visible,
.ix-filter-row:focus-visible,
.ix-rail-dot:focus-visible {
  outline: 2px solid var(--ix-accent-memory);
  outline-offset: 1px;
}

.ix-outline-row {
  display: flex;
  width: 100%;
  align-items: flex-start;
  gap: 0.4375rem;
  border-radius: 6px;
  border-left: 2px solid transparent;
  padding: 0.375rem 0.375rem 0.375rem 0.3125rem;
  text-align: left;
  transition: background-color 120ms, opacity 120ms;
}

.ix-outline-row:hover {
  background: var(--ix-raised);
}

.ix-outline-row-active {
  border-left-color: var(--ix-accent-memory);
  background: var(--ix-memory-tint);
}

.ix-outline-row-dim {
  opacity: 0.4;
}

.ix-outline-row-highlight {
  background: color-mix(in srgb, var(--ix-memory) 7%, transparent);
}

.ix-outline-dot {
  display: inline-flex;
  width: 0.75rem;
  flex: none;
  align-items: center;
  justify-content: center;
  padding-top: 0.1875rem;
}

.ix-outline-num {
  width: 0.75rem;
  flex: none;
  padding-top: 0.0625rem;
  font-size: 0.6875rem;
  line-height: 1rem;
  color: var(--ix-fg-3);
}

.ix-outline-section {
  margin-top: 0.875rem;
  border-top: 1px solid var(--ix-line-subtle);
  padding-top: 0.625rem;
}

.ix-outline-label {
  margin-bottom: 0.25rem;
  font-size: 0.625rem;
  line-height: 1rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ix-fg-3);
}

.ix-filter-row {
  display: flex;
  width: 100%;
  align-items: baseline;
  gap: 0.375rem;
  border-radius: 5px;
  padding: 0.25rem 0.375rem;
  font-size: 0.6875rem;
  line-height: 1rem;
  color: var(--ix-fg-2);
  text-align: left;
  transition: background-color 120ms, color 120ms;
}

.ix-filter-row:hover {
  background: var(--ix-raised);
  color: var(--ix-fg-1);
}

.ix-filter-row-active {
  background: var(--ix-memory-tint);
  color: var(--ix-fg-1);
}

/* Rail */
.ix-outline-rail {
  position: sticky;
  top: calc(3rem + 1rem);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  padding-top: 0.25rem;
}

.ix-rail-cap {
  display: inline-flex;
  width: 1.5rem;
  height: 1.5rem;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: var(--ix-raised);
  color: var(--ix-fg-3);
  margin-bottom: 0.25rem;
}

.ix-rail-dot {
  display: inline-flex;
  width: 1.75rem;
  height: 1.75rem;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--ix-line-subtle);
  border-radius: 7px;
  background: var(--ix-surface);
  transition: border-color 120ms, background-color 120ms, opacity 120ms;
}

.ix-rail-dot:hover {
  border-color: var(--ix-line-strong);
}

.ix-rail-dot-active {
  border-color: var(--ix-accent-memory);
  background: var(--ix-memory-tint);
}

.ix-rail-dot-dim {
  opacity: 0.4;
}

.ix-outline-rail {
  display: none;
}

@media (min-width: 1280px) and (max-width: 1439px) {
  .ix-outline-full {
    display: none;
  }

  .ix-outline-rail {
    display: flex;
  }
}

@media (min-width: 1440px) {
  .ix-outline-full-collapsed {
    display: none;
  }

  .ix-outline-full-collapsed + .ix-outline-rail {
    display: flex;
  }
}

@media (max-width: 1279px) {
  .ix-outline {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ix-outline-row,
  .ix-filter-row,
  .ix-rail-dot,
  .ix-toggle-button {
    transition-duration: 1ms;
  }
}
</style>
