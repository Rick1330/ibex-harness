<script setup lang="ts">
import { computed } from "vue"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { PreviewSession, SessionRound } from "@/lib/session-preview"
import { formatMs, formatOffset, outcomeLabel, outcomeTone, roundOffsetMs, sessionWallTimeMs } from "@/lib/session-detail"

const props = defineProps<{
  session: PreviewSession
  rounds: SessionRound[]
  selectedIndex: number
}>()

const emit = defineEmits<{ select: [index: number] }>()

const wallMs = computed(() => Math.max(1, sessionWallTimeMs(props.session)))
const driftCount = computed(() => props.rounds.filter((round) => round.drift).length)

/** Five evenly spaced labels keep the scale readable at every width. */
const axisTicks = computed(() => {
  const fractions = [0, 0.25, 0.5, 0.75, 1]
  const ticks = fractions.map((fraction) => Math.round(wallMs.value * fraction))
  ticks[ticks.length - 1] = wallMs.value
  return [...new Set(ticks)]
})

function left(offsetMs: number): string {
  return `${Math.min(100, Math.max(0, (offsetMs / wallMs.value) * 100))}%`
}

function tickLabel(tick: number): string {
  if (tick === wallMs.value) return formatMs(wallMs.value)
  if (tick === 0) return "0s"
  return `${(tick / 1000).toFixed(1)}s`
}

function toneColor(round: SessionRound): string {
  const tone = outcomeTone(round.outcome)
  if (tone === "destructive") return "var(--ix-crit)"
  if (tone === "warning") return "var(--ix-warn)"
  return "var(--ix-ok)"
}

function tooltip(round: SessionRound): string {
  const drift = round.drift ? " · drift advisory" : ""
  return `Turn ${round.index} · ${formatOffset(roundOffsetMs(props.session, round))} · ${round.latencyMs} ms · ${outcomeLabel(round.outcome)}${drift}`
}
</script>

<template>
  <section
    class="min-w-0"
    aria-label="Session timeline"
    title="Turn markers sit at each customer message; the gaps show time the agent was idle."
  >
    <div class="mb-1 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
      <p class="text-[0.625rem] leading-4 font-semibold tracking-[0.1em] text-fg-3 uppercase">
        Session timeline
        <span class="ml-1.5 font-normal tracking-normal normal-case max-sm:hidden">Turn starts</span>
      </p>
      <p class="text-[0.6875rem] leading-4 text-fg-3">
        <span class="font-mono text-fg-2 tabular-nums">{{ rounds.length }} turns</span>
        <span aria-hidden="true"> · </span>
        <span class="font-mono text-fg-2 tabular-nums">{{ formatMs(wallMs) }} wall</span>
        <template v-if="driftCount">
          <span aria-hidden="true"> · </span>
          <span class="text-warn">▲ {{ driftCount }} drift</span>
        </template>
      </p>
    </div>

    <div class="ix-timeline">
      <div class="ix-grid" aria-hidden="true">
        <span v-for="tick in axisTicks.slice(1, -1)" :key="tick" :style="{ left: left(tick) }" />
      </div>

      <Tooltip v-for="round in rounds" :key="round.id" :delay-duration="120">
        <TooltipTrigger as-child>
          <button
            type="button"
            class="ix-turn"
            :class="selectedIndex === round.index && 'ix-turn-active'"
            :style="{ left: left(roundOffsetMs(session, round)) }"
            :aria-label="`Turn ${round.index}: ${tooltip(round)}`"
            :aria-current="selectedIndex === round.index ? 'true' : undefined"
            @click="emit('select', round.index)"
          >
            <span v-if="round.drift" class="ix-drift-mark" aria-hidden="true">▲</span>
            <span class="ix-turn-dot" :style="{ '--ix-turn-tone': toneColor(round) }">
              <span class="ix-turn-number">{{ round.index }}</span>
            </span>
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" :side-offset="8" class="!text-xs">{{ tooltip(round) }}</TooltipContent>
      </Tooltip>
    </div>

    <div class="ix-axis" aria-hidden="true">
      <span
        v-for="tick in axisTicks"
        :key="`axis-${tick}`"
        class="ix-axis-tick"
        :style="{ left: left(tick) }"
      >{{ tickLabel(tick) }}</span>
    </div>
  </section>
</template>

<style scoped>
.ix-timeline {
  position: relative;
  height: 2.25rem;
  border-radius: 8px;
  background: var(--ix-surface);
  box-shadow: inset 0 0 0 1px var(--ix-line-subtle);
}

.ix-grid {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.ix-grid span {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: color-mix(in srgb, var(--ix-line-subtle) 70%, transparent);
}

.ix-turn {
  position: absolute;
  top: 50%;
  z-index: 2;
  display: inline-flex;
  transform: translate(-50%, -50%);
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  padding: 0.1875rem;
  transition: background-color 150ms;
}

.ix-turn:hover {
  background: var(--ix-raised);
}

.ix-turn:focus-visible {
  outline: 2px solid var(--ix-accent-memory);
  outline-offset: 1px;
}

.ix-turn-dot {
  display: inline-flex;
  width: 1.5rem;
  height: 1.5rem;
  align-items: center;
  justify-content: center;
  border: 1.5px solid color-mix(in srgb, var(--ix-turn-tone) 70%, var(--ix-line));
  border-radius: 9999px;
  background: color-mix(in srgb, var(--ix-turn-tone) 14%, var(--ix-surface));
  box-shadow: 0 0 0 3px var(--ix-surface);
  transition: border-color 150ms, background-color 150ms, box-shadow 150ms;
}

.ix-turn-active .ix-turn-dot {
  border-color: var(--ix-turn-tone);
  background: color-mix(in srgb, var(--ix-turn-tone) 24%, var(--ix-surface));
  box-shadow: 0 0 0 3px var(--ix-surface), 0 0 0 5px color-mix(in srgb, var(--ix-accent-memory) 55%, transparent);
}

.ix-turn-number {
  font-family: var(--font-mono);
  font-size: 0.625rem;
  line-height: 1;
  font-weight: 600;
  color: var(--ix-fg-1);
  font-variant-numeric: tabular-nums;
}

.ix-drift-mark {
  position: absolute;
  top: -0.4375rem;
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.5rem;
  line-height: 1;
  color: var(--ix-warn);
}

.ix-axis {
  position: relative;
  height: 1rem;
  margin-top: 0.125rem;
  font-family: var(--font-mono);
  font-size: 0.5625rem;
  line-height: 1;
  color: var(--ix-fg-3);
  font-variant-numeric: tabular-nums;
}

.ix-axis-tick {
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  white-space: nowrap;
}

.ix-axis-tick:first-child {
  transform: none;
}

.ix-axis-tick:last-child {
  transform: translateX(-100%);
}


@media (prefers-reduced-motion: reduce) {
  .ix-turn,
  .ix-turn-dot {
    transition-duration: 1ms;
  }
}
</style>
