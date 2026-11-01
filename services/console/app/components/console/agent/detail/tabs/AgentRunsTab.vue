<script setup lang="ts">
import { computed, ref } from "vue"
import { ArrowUpRight, ChevronDown, Search } from "@lucide/vue"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import MemoryInfoHint from "@/components/console/memory/primitives/MemoryInfoHint.vue"
import { useAgentTabQueryBoolean, useAgentTabQueryString } from "@/composables/useAgentTabQuery"
import {
  formatAgentMoney,
  formatAgentRelative,
  formatAgentStamp,
  formatAgentTokens,
} from "@/lib/agent-detail"
import type { AgentDetail, AgentRun, EvidenceState, RunOutcome } from "@/lib/agent-preview"
import BrandIcon from "@/components/console/BrandIcon.vue"

const props = defineProps<{ agent: AgentDetail }>()

const STATUS_OPTIONS = ["running", "succeeded", "failed", "retried", "cancelled"] as const
const EVIDENCE_OPTIONS = ["full", "partial", "sampled", "none"] as const

const search = useAgentTabQueryString("rq")
const status = useAgentTabQueryString("rstatus")
const evidence = useAgentTabQueryString("revidence")
const toolErrorsOnly = useAgentTabQueryBoolean("rtool")
const expanded = ref<string | null>(null)

const retriedCount = computed(() => props.agent.runsData.filter((run) => run.retried).length)

const filtered = computed(() =>
  props.agent.runsData.filter((run) => {
    const needle = search.value.trim().toLowerCase()
    if (needle && !`${run.id} ${run.sessionId}`.toLowerCase().includes(needle)) return false
    if (status.value === "retried" && !run.retried) return false
    if (status.value && status.value !== "retried" && run.status !== status.value) return false
    if (evidence.value && run.evidence !== evidence.value) return false
    if (toolErrorsOnly.value && !run.failedTool) return false
    return true
  }),
)

type StatusFilter = (typeof STATUS_OPTIONS)[number] | "";

const summary = computed(() => [
  { label: "Succeeded", value: props.agent.runsData.filter((run) => run.status === "succeeded").length, filter: "succeeded" as const },
  { label: "Failed", value: props.agent.runsData.filter((run) => run.status === "failed").length, filter: "failed" as const },
  { label: "Retried", value: retriedCount.value, filter: "retried" as const },
  { label: "p95", value: props.agent.stats.p95Ms === null ? null : `${(props.agent.stats.p95Ms / 1000).toFixed(1)}s`, filter: null },
])

function applySummaryFilter(filter: string | null): void {
  status.value = (filter ?? "") as StatusFilter
}

function outcomeTone(status: RunOutcome): string {
  if (status === "failed" || status === "cancelled") return "text-crit"
  if (status === "running") return "text-fg-2"
  return "text-ok"
}

function spanTone(kind: AgentRun["spans"][number]["kind"]): string {
  if (kind === "llm") return "bg-viz-2"
  if (kind === "tool") return "bg-viz-3"
  if (kind === "retrieval") return "bg-memory"
  if (kind === "policy") return "bg-viz-4"
  return "bg-fg-off"
}

const runSpanTotal = (run: AgentRun): number =>
  Math.max(1, ...run.spans.map((span) => span.offsetMs + span.durationMs))

const evidenceLabel: Record<EvidenceState, string> = {
  full: "full",
  partial: "partial",
  sampled: "sampled",
  none: "none",
}
</script>

<template>
  <div class="min-w-0 space-y-5">
    <div class="grid gap-3 sm:grid-cols-4">
      <button
        v-for="tile in summary"
        :key="tile.label"
        type="button"
        class="flex min-w-0 flex-col gap-0.5 rounded-lg border px-4 py-3 text-left transition-colors"
        :class="tile.label === 'Failed' && tile.value ? 'border-crit/30 bg-crit-tint/30' : 'border-line-subtle bg-surface-1 hover:border-line'"
        @click="applySummaryFilter(tile.filter)"
      >
        <span class="text-xs leading-4 text-fg-3">{{ tile.label }}</span>
        <span class="font-mono text-lg leading-6 font-semibold tabular-nums" :class="tile.label === 'Failed' && tile.value ? 'text-crit' : 'text-fg-1'">
          {{ tile.value ?? "—" }}
        </span>
      </button>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <div class="relative min-w-48 flex-1 sm:max-w-64">
        <Search :size="13" :stroke-width="1.9" class="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-fg-3" aria-hidden="true" />
        <input v-model="search" type="search" placeholder="Search run or session ID" aria-label="Search runs" class="ix-input h-8 pl-8 text-xs" >
      </div>
      <select v-model="status" aria-label="Filter by status" class="ix-input h-8 w-auto text-xs">
        <option value="">All statuses</option>
        <option v-for="option in STATUS_OPTIONS" :key="option" :value="option">{{ option }}</option>
      </select>
      <select v-model="evidence" aria-label="Filter by evidence" class="ix-input h-8 w-auto text-xs">
        <option value="">All evidence</option>
        <option v-for="option in EVIDENCE_OPTIONS" :key="option" :value="option">{{ option }}</option>
      </select>
      <label class="inline-flex h-8 items-center gap-1.5 text-xs text-fg-2">
        <input v-model="toolErrorsOnly" type="checkbox" class="accent-accent-memory" >
        Has tool error
      </label>
      <span class="ml-auto text-xs text-fg-3">{{ filtered.length }} runs</span>
    </div>

    <div class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
      <div class="overflow-x-auto">
        <table class="ix-table" aria-label="Agent runs">
          <thead>
            <tr>
              <th scope="col" class="w-28">Status</th>
              <th scope="col" class="w-36">Run</th>
              <th scope="col" class="w-36">Session</th>
              <th scope="col" class="w-24">Turn</th>
              <th scope="col" class="w-24">Started</th>
              <th scope="col" class="w-28">Duration</th>
              <th scope="col" class="w-32">Model</th>
              <th scope="col" class="w-40">Tokens</th>
              <th scope="col" class="w-20 text-right">Cost</th>
              <th scope="col" class="w-32">Tools</th>
              <th scope="col" class="w-20">Evidence</th>
              <th scope="col" class="w-8"><span class="sr-only">Expand</span></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="run in filtered" :key="run.id">
              <tr :class="run.status === 'failed' ? 'run-failed' : ''">
                <td>
                  <span class="inline-flex items-center gap-1.5 text-xs font-medium" :class="outcomeTone(run.status)">
                    <span v-if="run.status === 'running'" class="size-1.5 animate-pulse rounded-full bg-fg-2" aria-hidden="true" />
                    <span v-else class="size-1.5 rounded-full" :class="run.status === 'succeeded' ? 'bg-ok' : run.status === 'failed' ? 'bg-crit' : 'bg-fg-3'" aria-hidden="true" />
                    {{ run.status }}
                  </span>
                </td>
                <td class="font-mono text-xs text-fg-2">{{ run.id }}</td>
                <td>
                  <NuxtLink
                    :to="`/sessions/${encodeURIComponent(run.sessionId)}`"
                    class="font-mono text-xs text-fg-2 underline decoration-transparent underline-offset-3 transition-colors hover:text-accent-memory hover:decoration-accent-memory"
                  >
                    {{ run.sessionId }}
                  </NuxtLink>
                </td>
                <td>
                  <NuxtLink :to="`/sessions/${encodeURIComponent(run.sessionId)}`" class="font-mono text-xs text-fg-3 tabular-nums hover:text-accent-memory">
                    #{{ run.turn }}
                  </NuxtLink>
                </td>
                <td>
                  <Tooltip :delay-duration="150">
                    <TooltipTrigger as-child>
                      <span class="cursor-default text-xs whitespace-nowrap text-fg-2">{{ formatAgentRelative(run.startedAt) }}</span>
                    </TooltipTrigger>
                    <TooltipContent side="top" class="!font-mono !text-xs">{{ formatAgentStamp(run.startedAt) }}</TooltipContent>
                  </Tooltip>
                </td>
                <td>
                  <span class="flex items-center gap-2 font-mono text-xs text-fg-1 tabular-nums">
                    <span class="h-1 w-12 overflow-hidden rounded-full bg-raised" aria-hidden="true">
                      <span
                        class="block h-full rounded-full"
                        :class="run.durationMs > (agent.stats.p95Ms ?? Infinity) ? 'bg-warn' : 'bg-fg-off'"
                        :style="{ width: `${Math.min(100, (run.durationMs / runSpanTotal(run)) * 100)}%` }"
                      />
                    </span>
                    {{ (run.durationMs / 1000).toFixed(1) }}s
                  </span>
                </td>
                <td><span class="inline-flex items-center gap-1.5 font-mono text-[0.6875rem] text-fg-3"><BrandIcon :id="run.model" :size="12" :label="`${run.model} logo`" />{{ run.model }}</span></td>
                <td class="font-mono text-[0.6875rem] text-fg-3 tabular-nums">{{ formatAgentTokens(run.tokensIn, run.tokensOut) }}</td>
                <td class="text-right font-mono text-xs text-fg-1 tabular-nums">{{ formatAgentMoney(run.costUsd) }}</td>
                <td class="text-xs text-fg-3">
                  {{ run.tools.length }} <span v-if="run.tools.length" class="font-mono text-[0.625rem]">{{ run.tools.slice(0, 2).join(", ") }}</span>
                </td>
                <td>
                  <span
                    class="inline-flex h-4.5 items-center rounded border px-1.5 text-[0.625rem]"
                    :class="run.evidence === 'full' ? 'border-line text-fg-2' : 'border-transparent text-warn'"
                  >
                    {{ evidenceLabel[run.evidence] }}
                  </span>
                </td>
                <td class="text-right">
                  <button
                    type="button"
                    class="inline-flex size-6 items-center justify-center rounded text-fg-3 transition-colors hover:bg-raised hover:text-fg-1"
                    :aria-expanded="expanded === run.id"
                    :aria-label="`Toggle details for ${run.id}`"
                    @click="expanded = expanded === run.id ? null : run.id"
                  >
                    <ChevronDown :size="13" :stroke-width="1.9" class="transition-transform" :class="expanded === run.id && 'rotate-180'" aria-hidden="true" />
                  </button>
                </td>
              </tr>
              <tr v-if="expanded === run.id">
                <td colspan="12" class="!h-auto bg-raised/40 !py-3">
                  <div class="min-w-0 pl-2">
                    <p class="text-[0.6875rem] font-semibold tracking-[0.06em] text-fg-3 uppercase">Span waterfall</p>
                    <div class="mt-2 flex flex-col gap-1" style="min-width: 24rem">
                      <div v-for="span in run.spans" :key="span.id" class="flex items-center gap-2">
                        <span class="w-28 shrink-0 truncate font-mono text-[0.625rem] text-fg-3">{{ span.label }}</span>
                        <span class="relative h-3 flex-1 rounded-sm bg-canvas">
                          <span
                            class="absolute inset-y-0 rounded-sm"
                            :class="[spanTone(span.kind), span.status === 'error' && 'outline outline-1 outline-crit']"
                            :style="{ left: `${(span.offsetMs / runSpanTotal(run)) * 100}%`, width: `${Math.max(1, (span.durationMs / runSpanTotal(run)) * 100)}%` }"
                          />
                        </span>
                        <span class="w-14 shrink-0 text-right font-mono text-[0.625rem] text-fg-3 tabular-nums">{{ span.durationMs }} ms</span>
                      </div>
                    </div>
                    <p v-if="run.error" class="mt-3 rounded-lg border border-crit/30 bg-crit-tint px-3 py-2 text-xs leading-4 text-crit">
                      {{ run.error }}
                    </p>
                    <div class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
                      <NuxtLink
                        :to="`/sessions/${encodeURIComponent(run.sessionId)}`"
                        class="inline-flex items-center gap-1 font-medium text-fg-2 underline decoration-line-strong underline-offset-3 hover:text-accent-memory"
                      >
                        Open session
                        <ArrowUpRight :size="11" :stroke-width="1.9" aria-hidden="true" />
                      </NuxtLink>
                      <NuxtLink to="/explore" class="inline-flex items-center gap-1 font-medium text-fg-2 underline decoration-line-strong underline-offset-3 hover:text-accent-memory">
                        Open in Explore
                        <ArrowUpRight :size="11" :stroke-width="1.9" aria-hidden="true" />
                      </NuxtLink>
                      <span class="font-mono text-[0.625rem] text-fg-3">{{ run.id }} · {{ run.sessionId }} · turn {{ run.turn }}</span>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
            <tr v-if="!filtered.length">
              <td colspan="12" class="!h-24 text-center text-xs text-fg-3">
                {{ agent.runsData.length ? "No runs match these filters." : "This agent hasn't run yet." }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <p class="flex items-center gap-1.5 text-xs leading-4 text-fg-3">
      Evidence is shown as recorded. Partial or sampled runs are never filled in.
      <MemoryInfoHint label="Why?">
        <p class="font-medium text-fg-1">Evidence states</p>
        <p class="mt-1">
          Evidence is the trace completeness recorded for the run: full, partial, sampled, or none. Missing spans are
          never reconstructed or estimated.
        </p>
      </MemoryInfoHint>
    </p>
  </div>
</template>

<style scoped>
.run-failed {
  box-shadow: inset 3px 0 0 var(--row-critical-edge);
}
</style>
