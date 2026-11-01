<script setup lang="ts">
import { computed } from "vue"
import type { PreviewSession, SessionRound } from "@/lib/session-preview"
import {
  formatCount,
  formatCostShort,
  formatMs,
  sessionAgentTimeMs,
  sessionFailureCount,
  sessionTotals,
  sessionWallTimeMs,
  totalToolCalls,
  turnFailedTools,
} from "@/lib/session-detail"
import MemoryStatTile from "@/components/console/memory/primitives/MemoryStatTile.vue"

const props = defineProps<{
  session: PreviewSession
  rounds: SessionRound[]
}>()

const totals = computed(() => sessionTotals(props.session, props.rounds))
const agentTime = computed(() => sessionAgentTimeMs(props.rounds))
const wallTime = computed(() => sessionWallTimeMs(props.session))
const toolCount = computed(() => totalToolCalls(props.rounds))
const failedTools = computed(() => props.rounds.reduce((sum, round) => sum + turnFailedTools(round), 0))
const failures = computed(() => sessionFailureCount(props.rounds))
const succeeded = computed(() => props.rounds.length - failures.value)
const tokenShare = computed(() => {
  const total = totals.value.tokensIn + totals.value.tokensOut
  return total > 0 ? Math.max(4, Math.round((totals.value.tokensOut / total) * 100)) : 0
})
const coverageHint = computed(
  () =>
    `Context coverage ${props.session.coverage}: ${props.rounds.length} of ${props.rounds.length} rendered turns carried the reviewed directive and at least one retrieved memory.`,
)
</script>

<template>
  <section
    class="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-[repeat(4,minmax(0,1fr))_minmax(0,1.35fr)_minmax(0,1fr)]"
    aria-label="Session totals"
  >
    <MemoryStatTile
      compact
      label="Agent time"
      :value="formatMs(agentTime)"
      :helper="`sum of ${rounds.length} responses`"
      :title="`Sum of the ${rounds.length} rendered response latencies: ${rounds.map((round) => round.latencyMs).join(' + ')} ms`"
    />
    <MemoryStatTile
      compact
      label="Wall time"
      :value="formatMs(wallTime)"
      helper="first to last message"
      title="First customer message to last response, including typing gaps."
    />
    <MemoryStatTile
      compact
      label="Turns"
      :value="String(rounds.length)"
      :helper="failures === 0 ? `${succeeded} ok` : `${succeeded} ok · ${failures} failed`"
      :title="coverageHint"
    />
    <MemoryStatTile
      compact
      label="Tool calls"
      :value="`${toolCount} · ${failedTools} failed`"
      :title="`${toolCount} tool calls across ${rounds.length} turns; ${failedTools} returned an error.`"
    />
    <MemoryStatTile
      compact
      label="Tokens"
      :value="totals.tokensLabel"
      :title="`${formatCount(totals.tokensIn)} input tokens · ${formatCount(totals.tokensOut)} output tokens`"
    >
      <span class="flex h-1.5 w-full overflow-hidden rounded-full bg-raised" aria-hidden="true">
        <span class="h-full bg-memory" :style="{ width: `${100 - tokenShare}%` }" />
        <span class="h-full bg-accent-memory/45" :style="{ width: `${tokenShare}%` }" />
      </span>
    </MemoryStatTile>
    <MemoryStatTile
      compact
      label="Cost"
      :value="formatCostShort(totals.costUsd)"
      :helper="totals.complete ? 'all rendered turns' : 'recorded session total'"
      :title="`Exact recorded cost ${totals.costExact}`"
    />
  </section>
</template>
