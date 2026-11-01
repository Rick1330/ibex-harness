<script setup lang="ts">
import { computed } from "vue"
import type { PublicOperatorTraceDetail } from "~~/shared/operator/public"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernPendingData from "@/components/console/govern/primitives/GovernPendingData.vue"
import { formatDuration, formatNumber } from "@/lib/format"
import { formatGovernNumber, formatGovernPercent } from "@/lib/govern-format"
import { EXPLORE_TRACE_DETAIL_CONTRACT, exclusionClass, exclusionLabel, exclusionMeaning } from "@/lib/explore-view"

const props = defineProps<{ detail: PublicOperatorTraceDetail }>()

const assembly = computed(() => props.detail.assembly)
const candidates = computed(() => props.detail.candidates)
const directive = computed(() => props.detail.directive)

const unavailable = computed(() => new Set<string>(props.detail.unavailable_sections))

function isUnavailable(section: string): boolean {
  return unavailable.value.has(section)
}

const stages = computed(() => {
  const value = assembly.value
  if (!value) return []
  return [
    { key: "budget", label: "Budget calculation", ms: value.budget_calculation_ms, meaning: "Sizing the context window before anything was retrieved." },
    { key: "directive", label: "Directive load", ms: value.directive_load_ms, meaning: "Reading the directive version this run applied." },
    { key: "hot", label: "Hot memory retrieval", ms: value.hot_memory_retrieval_ms, meaning: "Retrieval from the always-loaded memory set." },
    { key: "cold", label: "Cold memory retrieval", ms: value.cold_memory_retrieval_ms, meaning: "Retrieval that had to leave the cache to answer." },
    { key: "ranking", label: "Ranking", ms: value.ranking_ms, meaning: "Ordering the candidates that survived retrieval." },
    { key: "packing", label: "Packing", ms: value.packing_ms, meaning: "Choosing which candidates fit the remaining budget." },
    { key: "formatting", label: "Formatting", ms: value.formatting_ms, meaning: "Rendering the packed context into the prompt shape." },
  ]
})

const stageTotal = computed(() => stages.value.reduce((sum, stage) => sum + stage.ms, 0))
const reportedTotalMs = computed(() => assembly.value?.total_ms ?? null)

/** The stages are recorded independently, so their sum is shown next to the reported total, never instead of it. */
function stageShare(ms: number): string {
  if (!reportedTotalMs.value) return "—"
  return formatGovernPercent((ms / reportedTotalMs.value) * 100, 1)
}

const rankedCandidates = computed(() =>
  [...candidates.value].sort((left, right) => {
    const leftRank = left.final_rank ?? Number.MAX_SAFE_INTEGER
    const rightRank = right.final_rank ?? Number.MAX_SAFE_INTEGER
    if (leftRank !== rightRank) return leftRank - rightRank
    return left.retrieval_rank - right.retrieval_rank
  }),
)

/** `included` is the assembler's own code for "this candidate was packed"; anything else was left out. */
const notPackedCount = computed(() => candidates.value.filter((candidate) => candidate.exclusion !== "included").length)
</script>

<template>
  <section class="flex min-w-0 flex-col gap-3" aria-label="Context assembly">
    <!-- Assembly timings -->
    <div class="min-w-0">
      <p class="mb-1.5 text-xs font-medium text-fg-1">Assembly stage timings</p>
      <div v-if="assembly && stages.length" class="min-w-0 overflow-hidden rounded-lg border border-line-subtle bg-surface">
        <div class="ix-scroll overflow-x-auto" aria-label="Assembly stage timings table">
          <table class="ix-agent-table" style="min-width: 620px">
            <thead>
              <tr>
                <th scope="col">Stage</th>
                <th scope="col" class="text-right">Recorded</th>
                <th scope="col" class="text-right">Share of reported total</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="stage in stages" :key="stage.key">
                <td class="text-xs text-fg-1" :title="stage.meaning">{{ stage.label }}</td>
                <td class="text-right font-mono text-xs text-fg-1 tabular-nums">{{ formatDuration(stage.ms) }}</td>
                <td class="text-right font-mono text-xs text-fg-3 tabular-nums">{{ stageShare(stage.ms) }}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr class="border-t border-line-subtle">
                <td class="text-xs text-fg-2">Stages summed</td>
                <td class="text-right font-mono text-xs text-fg-1 tabular-nums">{{ formatDuration(stageTotal) }}</td>
                <td class="text-right font-mono text-xs text-fg-3 tabular-nums">
                  reported total {{ reportedTotalMs === null ? "Not recorded" : formatDuration(reportedTotalMs) }}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
        <p class="border-t border-line-subtle px-3.5 py-2 text-[0.6875rem] leading-4 text-fg-3">
          {{ formatGovernNumber(assembly.candidates_evaluated) }} candidates were evaluated by the assembler.
        </p>
      </div>
      <GovernPendingData
        v-else
        title="Context assembly timings"
        :contract="EXPLORE_TRACE_DETAIL_CONTRACT"
        description="This run returned no assembly record. The stages are not estimated from the run's total duration."
      />
    </div>

    <!-- Directive -->
    <div class="min-w-0">
      <p class="mb-1.5 text-xs font-medium text-fg-1">Directive applied</p>
      <div v-if="directive" class="min-w-0 rounded-lg border border-line-subtle bg-surface px-3.5 py-2.5">
        <dl class="flex flex-col gap-1.5 text-xs">
          <div class="flex items-baseline justify-between gap-3">
            <dt class="shrink-0 text-fg-3" title="The version id the assembler loaded for this run.">Version id</dt>
            <dd class="min-w-0">
              <GovernCopyId
                v-if="directive.directive_version_id"
                :id="directive.directive_version_id"
                label="Directive version id"
                truncate
              />
              <span v-else class="text-right font-mono text-[0.6875rem] text-fg-3">Not recorded</span>
            </dd>
          </div>
          <div class="flex items-baseline justify-between gap-3">
            <dt class="shrink-0 text-fg-3" title="Content hash of the directive text this run was assembled with.">Content hash</dt>
            <dd class="min-w-0">
              <GovernCopyId v-if="directive.content_hash" :id="directive.content_hash" label="Content hash" truncate />
              <span v-else class="text-right font-mono text-[0.6875rem] text-fg-3">Not recorded</span>
            </dd>
          </div>
          <div class="flex items-baseline justify-between gap-3">
            <dt class="shrink-0 text-fg-3" title="Schema the directive payload was validated against.">Schema</dt>
            <dd class="min-w-0 truncate text-right font-mono text-xs text-fg-1">{{ directive.schema_version }}</dd>
          </div>
        </dl>
      </div>
      <GovernPendingData
        v-else
        title="Directive version"
        :contract="EXPLORE_TRACE_DETAIL_CONTRACT"
        description="No directive metadata was attached to this run, so which instruction set applied is unknown rather than default."
      />
    </div>

    <!-- Candidates -->
    <div class="min-w-0">
      <p class="mb-1.5 flex flex-wrap items-baseline justify-between gap-2">
        <span class="text-xs font-medium text-fg-1">Retrieval candidates</span>
        <span class="font-mono text-[0.6875rem] leading-4 text-fg-3">
          {{ formatGovernNumber(candidates.length) }} returned
          <span v-if="notPackedCount"> · {{ formatGovernNumber(notPackedCount) }} not packed</span>
        </span>
      </p>

      <div v-if="candidates.length" class="min-w-0 ix-scroll overflow-x-auto rounded-lg border border-line-subtle">
        <table class="ix-agent-table" style="min-width: 860px" aria-label="Retrieval candidates">
          <thead>
            <tr>
              <th scope="col">Memory id</th>
              <th scope="col" class="text-right">Retrieved at</th>
              <th scope="col" class="text-right">Final rank</th>
              <th scope="col" class="text-right">Movement</th>
              <th scope="col">Category</th>
              <th scope="col" class="text-right">Tokens</th>
              <th scope="col">Exclusion</th>
              <th scope="col" class="text-right">Score</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="candidate in rankedCandidates" :key="candidate.memory_id">
              <td class="min-w-0"><GovernCopyId :id="candidate.memory_id" label="Memory id" truncate /></td>
              <td class="text-right font-mono text-xs text-fg-2 tabular-nums">{{ formatNumber(candidate.retrieval_rank) }}</td>
              <td class="text-right font-mono text-xs tabular-nums" :class="candidate.final_rank === null ? 'text-fg-3' : 'text-fg-1'">
                {{ candidate.final_rank === null ? "Not packed" : formatNumber(candidate.final_rank) }}
              </td>
              <td class="text-right font-mono text-xs tabular-nums" :class="candidate.delta_rank === null ? 'text-fg-3' : candidate.delta_rank > 0 ? 'text-ok' : candidate.delta_rank < 0 ? 'text-warn' : 'text-fg-2'">
                {{ candidate.delta_rank === null ? "—" : candidate.delta_rank > 0 ? `+${candidate.delta_rank}` : String(candidate.delta_rank) }}
              </td>
              <td class="truncate font-mono text-xs text-fg-2" :title="candidate.category ?? ''">{{ candidate.category ?? "Not recorded" }}</td>
              <td class="text-right font-mono text-xs text-fg-2 tabular-nums" :title="candidate.token_estimate === null ? 'No token estimate was recorded for this candidate' : 'Estimated tokens this candidate would have occupied'">
                {{ candidate.token_estimate === null ? "—" : formatNumber(candidate.token_estimate) }}
              </td>
              <td class="truncate text-xs" :class="exclusionClass(candidate.exclusion)" :title="`${candidate.exclusion} · ${exclusionMeaning(candidate.exclusion)}`">
                {{ exclusionLabel(candidate.exclusion) }}
              </td>
              <td class="text-right font-mono text-xs text-fg-1 tabular-nums" :title="`${candidate.score_schema}${candidate.composite_score === null ? ' · no score value returned' : ''}`">
                {{ candidate.composite_score === null ? "Not recorded" : candidate.composite_score.toFixed(3) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <GovernPendingData
        v-else
        title="Retrieval candidates"
        :contract="EXPLORE_TRACE_DETAIL_CONTRACT"
        description="No candidate rows were returned, so ranking cannot be shown or reconstructed for this run."
      />

      <p v-if="detail.score_schema_note" class="mt-1.5 text-[0.6875rem] leading-4 text-fg-3">
        Score schema note, verbatim: <code class="font-mono text-fg-2">{{ detail.score_schema_note }}</code>
      </p>

      <GovernCaveat v-if="isUnavailable('score_explanation')" tone="warning" title="Scores without a reason">
        The candidate rows carry composite scores, but this run marked score explanation unavailable. The number is shown
        because it was recorded; why it took that value is not knowable from this payload.
      </GovernCaveat>

      <GovernCaveat tone="lock" title="Candidate ids do not open the memory">
        These are the memory identifiers the assembler saw. The memories surface in this build reads from a preview set,
        so a live id has no record to open — the identifier is shown so it can be looked up through the API instead.
      </GovernCaveat>
    </div>
  </section>
</template>
