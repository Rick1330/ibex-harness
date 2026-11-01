<script setup lang="ts">
import { computed } from "vue"
import { ArrowRight, TriangleAlert } from "@lucide/vue"
import type { PreviewSession, SessionRound } from "@/lib/session-preview"
import { formatOffset, outcomeLabel, outcomeTone, roundOffsetMs } from "@/lib/session-detail"
import SessionStatusPill from "./primitives/SessionStatusPill.vue"

const props = defineProps<{
  session: PreviewSession
  rounds: SessionRound[]
  selectedIndex: number
}>()

const emit = defineEmits<{ select: [index: number] }>()

const rows = computed(() =>
  props.rounds.map((round) => ({
    round,
    offset: formatOffset(roundOffsetMs(props.session, round)),
    tone: outcomeTone(round.outcome),
    answer: round.assistantText.length > 140 ? `${round.assistantText.slice(0, 139).trimEnd()}…` : round.assistantText,
    tools: round.toolCalls.length,
    memories: round.memories.length,
  })),
)
</script>

<template>
  <div class="mx-auto w-full max-w-[760px] space-y-2">
    <button
      v-for="row in rows"
      :key="row.round.id"
      type="button"
      class="ix-turn-card"
      :class="selectedIndex === row.round.index && 'ix-turn-card-active'"
      @click="emit('select', row.round.index)"
    >
      <div class="flex items-start gap-2">
        <span class="mt-0.5 font-mono text-[0.6875rem] leading-4 text-fg-3 tabular-nums">Turn {{ row.round.index }}</span>
        <span class="mt-0.5 font-mono text-[0.625rem] leading-4 text-fg-3 tabular-nums">{{ row.offset }}</span>
        <SessionStatusPill class="ml-auto" :tone="row.tone" :label="outcomeLabel(row.round.outcome)" compact />
      </div>
      <p class="mt-1.5 text-[0.9375rem] leading-6 text-fg-1 text-pretty">{{ row.round.userText }}</p>
      <p class="mt-1 text-[0.8125rem] leading-5 text-fg-3 text-pretty">{{ row.answer }}</p>
      <div class="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[0.6875rem] leading-4 text-fg-3">
        <span class="font-mono tabular-nums">{{ row.round.latencyMs }} ms</span>
        <span aria-hidden="true">·</span>
        <span>{{ row.tools }} {{ row.tools === 1 ? "tool" : "tools" }}</span>
        <span aria-hidden="true">·</span>
        <span>{{ row.memories }} {{ row.memories === 1 ? "memory" : "memories" }}</span>
        <span v-if="row.round.drift" class="inline-flex items-center gap-1 text-warn">
          <TriangleAlert :size="10" :stroke-width="2" aria-hidden="true" />
          Drift advisory
        </span>
        <span class="ml-auto inline-flex items-center gap-1 font-medium text-fg-2">
          Open turn
          <ArrowRight :size="11" :stroke-width="1.75" aria-hidden="true" />
        </span>
      </div>
    </button>
  </div>
</template>

<style scoped>
.ix-turn-card {
  display: block;
  width: 100%;
  border: 1px solid var(--ix-line-subtle);
  border-radius: 10px;
  background: var(--ix-surface);
  padding: 0.75rem 0.875rem;
  text-align: left;
  transition: border-color 120ms, background-color 120ms;
}

.ix-turn-card:hover {
  border-color: var(--ix-line-strong);
}

.ix-turn-card-active {
  border-color: var(--ix-accent-memory);
  background: color-mix(in srgb, var(--ix-memory) 5%, var(--ix-surface));
}

.ix-turn-card:focus-visible {
  outline: 2px solid var(--ix-accent-memory);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  .ix-turn-card {
    transition-duration: 1ms;
  }
}
</style>
