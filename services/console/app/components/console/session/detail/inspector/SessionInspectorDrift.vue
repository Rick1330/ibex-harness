<script setup lang="ts">
import { computed } from "vue"
import { ArrowRight, Circle, Lock, ShieldCheck } from "@lucide/vue"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { SessionRound } from "@/lib/session-preview"
import { driftState } from "@/lib/session-detail"
import MemoryScoreBar from "@/components/console/memory/primitives/MemoryScoreBar.vue"
import SessionCaveat from "../primitives/SessionCaveat.vue"
import SessionKeyValueList from "../primitives/SessionKeyValueList.vue"
import SessionRawRecord from "../primitives/SessionRawRecord.vue"
import SessionSectionLabel from "../primitives/SessionSectionLabel.vue"

const props = defineProps<{
  round: SessionRound
  rounds: SessionRound[]
}>()

const emit = defineEmits<{
  transcript: []
  selectTurn: [index: number]
}>()

const state = computed(() => driftState(props.round))
const drift = computed(() => props.round.drift)
const check = computed(() => props.round.driftCheck)
const flagged = computed(() => props.rounds.filter((entry) => entry.drift !== null))

const reason = computed(() => drift.value?.detail?.trim() || "Advisory raised; no reason recorded.")

const advisoryRows = computed(() => {
  if (!drift.value) return []
  return [
    { label: "Compared with", value: drift.value.baseline },
    { label: "Metric", value: drift.value.metric },
    { label: "Detected by", value: `${drift.value.evaluator} · +${drift.value.checkedAtOffsetMs} ms`, mono: true },
    { label: "Scope", value: drift.value.scope },
  ]
})

const cleanRows = computed(() => {
  if (!check.value) return []
  const rows = []
  if (check.value.evaluator) rows.push({ label: "Checked by", value: check.value.evaluator, mono: true })
  if (check.value.checkedAtOffsetMs !== null) rows.push({ label: "Checked at", value: `+${check.value.checkedAtOffsetMs} ms`, mono: true })
  if (check.value.detail) rows.push({ label: "Result", value: check.value.detail })
  return rows
})
</script>

<template>
  <div class="space-y-5">
    <template v-if="state === 'advisory' && drift">
      <div class="ix-advisory">
        <p class="flex items-start gap-2 text-sm leading-5 text-fg-1 text-pretty">
          <span class="mt-px text-warn" aria-hidden="true">▲</span>
          <span>{{ reason }}</span>
        </p>
        <SessionKeyValueList class="mt-2" :rows="advisoryRows" />
        <div v-if="drift.threshold > 0" class="mt-3">
          <div class="mb-1.5 flex items-baseline justify-between gap-2">
            <span class="font-mono text-xs text-fg-1 tabular-nums">measured {{ drift.measured.toFixed(2) }}</span>
            <span class="font-mono text-[0.6875rem] leading-4 text-fg-3 tabular-nums">threshold {{ drift.threshold.toFixed(2) }}</span>
          </div>
          <MemoryScoreBar
            :value="drift.measured"
            :threshold="drift.threshold"
            color="bg-warn"
            :label="`Measured ${drift.measured.toFixed(2)} against threshold ${drift.threshold.toFixed(2)}`"
          />
        </div>
        <div class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5">
          <button type="button" class="ix-inline-link" @click="emit('transcript')">
            Show in transcript
            <ArrowRight :size="11" :stroke-width="1.75" aria-hidden="true" />
          </button>
          <Tooltip :delay-duration="120">
            <TooltipTrigger as-child>
              <button type="button" class="ix-disabled-button" disabled aria-disabled="true">
                <Lock :size="11" :stroke-width="1.75" aria-hidden="true" />
                Compare with baseline
              </button>
            </TooltipTrigger>
            <TooltipContent side="top" :side-offset="6" class="!text-xs">Baseline comparison isn't available in this preview.</TooltipContent>
          </Tooltip>
        </div>
      </div>

      <SessionCaveat
        summary="Drift is advisory here."
        detail="It does not rewrite the directive or block the response."
      />
    </template>

    <template v-else-if="state === 'clean' && check">
      <div v-if="check.detail" class="flex items-start gap-2">
        <ShieldCheck :size="15" :stroke-width="1.8" class="mt-0.5 shrink-0 text-ok" aria-hidden="true" />
        <p class="text-[0.8125rem] leading-5 text-fg-2 text-pretty">{{ check.detail }}</p>
      </div>

      <div v-if="check.metric && check.measured !== null && check.threshold !== null" class="rounded-lg bg-surface px-3 py-2.5">
        <div class="mb-1.5 flex items-baseline justify-between gap-2">
          <span class="text-xs leading-4 text-fg-2">{{ check.metric }}</span>
          <span class="font-mono text-[0.6875rem] leading-4 text-fg-3 tabular-nums">threshold {{ check.threshold.toFixed(2) }}</span>
        </div>
        <div class="flex items-center gap-2">
          <MemoryScoreBar
            :value="check.measured"
            :threshold="check.threshold"
            color="bg-fg-3"
            :label="`Measured ${check.measured.toFixed(2)} against threshold ${check.threshold.toFixed(2)}`"
          />
          <span class="shrink-0 font-mono text-xs text-fg-2 tabular-nums">{{ check.measured.toFixed(2) }}</span>
        </div>
      </div>

      <section>
        <SessionSectionLabel>Evaluation</SessionSectionLabel>
        <SessionKeyValueList class="mt-1" :rows="cleanRows" />
      </section>
    </template>

    <template v-else>
      <div class="flex items-start gap-1.5">
        <Circle :size="13" :stroke-width="1.8" class="mt-1 shrink-0 text-fg-3" aria-hidden="true" />
        <SessionCaveat
          summary="No advisory doesn't mean no drift."
          detail="A missing advisory is neither a clean baseline nor a certification. Evaluation state is unavailable in this illustrative record."
        />
      </div>

      <SessionKeyValueList
        :rows="[{ label: 'Scope', value: 'This response only' }]"
      />
    </template>

    <section class="border-t border-line-subtle pt-3">
      <p class="flex flex-wrap items-center gap-x-1.5 text-xs leading-5 text-fg-3">
        <span class="text-fg-2">Session drift:</span>
        <span>{{ flagged.length }} of {{ rounds.length }} turns flagged</span>
        <template v-if="flagged.length">
          <span aria-hidden="true">·</span>
          <template v-for="(entry, index) in flagged" :key="entry.id">
            <button type="button" class="ix-inline-link" @click="emit('selectTurn', entry.index)">Turn {{ entry.index }}</button>
            <span v-if="index < flagged.length - 1" aria-hidden="true">·</span>
          </template>
        </template>
      </p>
    </section>

    <SessionRawRecord :value="drift ?? check ?? { state: 'not_checked' }" />
  </div>
</template>

<style scoped>
.ix-advisory {
  border: 1px solid color-mix(in srgb, var(--ix-warn) 30%, transparent);
  border-radius: 10px;
  background: var(--ix-warn-tint);
  padding: 0.75rem 0.875rem;
}

.ix-inline-link {
  display: inline-flex;
  align-items: center;
  gap: 0.1875rem;
  border-radius: 3px;
  font-size: 0.6875rem;
  line-height: 1rem;
  font-weight: 500;
  color: var(--ix-fg-2);
  text-decoration: underline;
  text-decoration-color: var(--ix-line-strong);
  text-underline-offset: 2px;
  transition: color 120ms;
}

.ix-inline-link:hover {
  color: var(--ix-fg-1);
}

.ix-inline-link:focus-visible {
  outline: 2px solid var(--ix-accent-memory);
  outline-offset: 2px;
}

.ix-disabled-button {
  display: inline-flex;
  height: 1.75rem;
  cursor: not-allowed;
  align-items: center;
  gap: 0.3125rem;
  border: 1px solid var(--ix-line-subtle);
  border-radius: 6px;
  background: transparent;
  padding: 0 0.5rem;
  font-size: 0.6875rem;
  line-height: 1;
  color: var(--ix-fg-3);
  opacity: 0.75;
}
</style>
