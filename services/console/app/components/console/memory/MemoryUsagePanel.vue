<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { ArrowUpRight, ChevronDown, SearchX } from "@lucide/vue"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { formatDayTimeUtc } from "@/lib/format"
import { memoryRelativeTime } from "@/lib/memory-preview"
import type { MemoryDetail, MemoryScoreTerm } from "@/lib/memory-detail-preview"
import MemoryOutcomePill from "./primitives/MemoryOutcomePill.vue"
import MemoryScoreBar from "./primitives/MemoryScoreBar.vue"
import MemoryEmptyValue from "./primitives/MemoryEmptyValue.vue"
import MemoryInfoHint from "./primitives/MemoryInfoHint.vue"

const props = defineProps<{ detail: MemoryDetail }>()

const retrieval = computed(() => props.detail.retrieval)
const lastRetrievedLabel = computed(() => props.detail.memory.lastRetrievedLabel)
const selected = ref<string | null>(null)
const includedCount = computed(() => retrieval.value.sessions.filter((session) => session.usage === "injected").length)
const linkedCount = computed(() => retrieval.value.sessions.length)
const inclusionRate = computed(() => (linkedCount.value ? Math.round((includedCount.value / linkedCount.value) * 100) : 0))

const terms = computed(() => retrieval.value.scoreTerms)
const contributions = computed(() =>
  terms.value.map((term) => ({ term, contribution: term.value * term.weight })),
)
const contributionTotal = computed(() => contributions.value.reduce((total, entry) => total + entry.contribution, 0))

const DOT: Record<string, string> = {
  relevance: "bg-viz-1",
  recency: "bg-viz-2",
  usefulness: "bg-viz-3",
  confidence: "bg-viz-4",
  frequency: "bg-viz-5",
}

function toggle(id: string): void {
  selected.value = selected.value === id ? null : id
}

function contributionColor(key: string): string {
  return DOT[key] ?? "bg-viz-5"
}

const hasSparkline = computed(() => retrieval.value.sparkline.some((point) => point.count > 0))
const sparklineMax = computed(() => Math.max(1, ...retrieval.value.sparkline.map((point) => point.count)))

// Composite contribution bar segments animate once on first view.
const mounted = ref(false)
onMounted(() => {
  requestAnimationFrame(() => {
    mounted.value = true
  })
})

function segmentStyle(term: MemoryScoreTerm, index: number): Record<string, string> {
  const width = (term.value * term.weight * 100) / Math.max(contributionTotal.value, 0.0001)
  return {
    width: mounted.value ? `${width}%` : "0%",
    background: `var(--ix-viz-${index + 1})`,
    transitionDelay: `${index * 40}ms`,
  }
}

function agentInitials(agent: string): string {
  return agent
    .split(/\s+/)
    .map((word) => word[0])
    .join("")
    .slice(0, 2)
    .toUpperCase()
}
</script>

<template>
  <div class="min-w-0 space-y-6">
    <div class="grid gap-3 sm:grid-cols-3 xl:grid-cols-5">
      <div class="rounded-lg border border-line-subtle bg-surface px-4 py-3">
        <p class="text-xs leading-4 text-fg-3">Retrieval events</p>
        <p class="mt-0.5 font-mono text-xl leading-7 font-semibold text-fg-1 tabular-nums">{{ retrieval.count }}</p>
      </div>
      <div class="rounded-lg border border-line-subtle bg-surface px-4 py-3">
        <p class="text-xs leading-4 text-fg-3">Linked sessions</p>
        <p class="mt-0.5 font-mono text-xl leading-7 font-semibold text-fg-1 tabular-nums">{{ linkedCount }}</p>
      </div>
      <div class="rounded-lg border border-line-subtle bg-surface px-4 py-3">
        <p class="text-xs leading-4 text-fg-3">Included in context</p>
        <p class="mt-0.5 font-mono text-xl leading-7 font-semibold text-fg-1 tabular-nums">{{ includedCount }}</p>
      </div>
      <div class="rounded-lg border border-line-subtle bg-surface px-4 py-3">
        <p class="text-xs leading-4 text-fg-3">Inclusion rate</p>
        <p class="mt-0.5 font-mono text-xl leading-7 font-semibold text-fg-1 tabular-nums">{{ inclusionRate }}%</p>
      </div>
      <div class="rounded-lg border border-line-subtle bg-surface px-4 py-3">
        <p class="text-xs leading-4 text-fg-3">Last retrieved</p>
        <p class="mt-0.5 truncate text-lg leading-7 font-semibold text-fg-1">
          <MemoryEmptyValue v-if="!lastRetrievedLabel" />
          <template v-else>{{ lastRetrievedLabel }}</template>
        </p>
      </div>
    </div>

    <section
      v-if="hasSparkline"
      aria-labelledby="usage-sparkline"
      class="rounded-lg border border-line-subtle bg-surface p-5"
    >
      <h2 id="usage-sparkline" class="text-sm leading-5 font-semibold text-fg-1">Retrievals over time</h2>
      <div class="mt-3 flex h-12 items-end gap-1" aria-hidden="true">
        <Tooltip v-for="point in retrieval.sparkline" :key="point.date" :delay-duration="100">
          <TooltipTrigger as-child>
            <span class="h-full flex-1 cursor-default rounded-sm">
              <span
                class="block h-full w-full rounded-sm bg-viz-1/70 transition-colors hover:bg-viz-1"
                :style="{ height: `${Math.max(4, (point.count / sparklineMax) * 100)}%` }"
              />
            </span>
          </TooltipTrigger>
          <TooltipContent side="top" class="!font-mono !text-xs !tabular-nums">
            {{ point.date }} · {{ point.count }}
          </TooltipContent>
        </Tooltip>
      </div>
    </section>

    <section aria-labelledby="usage-table" class="rounded-lg border border-line-subtle bg-surface">
      <div class="flex flex-wrap items-baseline justify-between gap-2 p-5 pb-3">
        <h2 id="usage-table" class="text-sm leading-5 font-semibold text-fg-1">Retrieval sessions</h2>
        <p class="flex items-center gap-1.5 text-xs leading-4 text-fg-3">
          Outcome is the retrieval decision for that event.
          <MemoryInfoHint label="About outcomes">
            <p class="font-medium text-fg-1">Inclusion is not influence</p>
            <p class="mt-1">
              “Included in context” means the memory was placed in the model context for that retrieval. Influence on the
              final answer is not measured. Per-event query text is not recorded in this preview.
            </p>
          </MemoryInfoHint>
        </p>
      </div>

      <div v-if="linkedCount" class="overflow-x-auto">
        <table class="ix-table" aria-label="Retrieval sessions for this memory">
          <thead>
            <tr>
              <th scope="col">Session</th>
              <th scope="col">Agent</th>
              <th scope="col">Rank</th>
              <th scope="col" class="min-w-40">Composite</th>
              <th scope="col">Outcome</th>
              <th scope="col">When</th>
              <th scope="col"><span class="sr-only">Expand</span></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="session in retrieval.sessions" :key="session.id">
              <tr :data-expanded="selected === session.id">
                <td class="min-w-56">
                  <NuxtLink
                    :to="`/sessions/${encodeURIComponent(session.id)}`"
                    class="block max-w-64 truncate text-[0.8125rem] font-medium text-fg-1 underline decoration-transparent underline-offset-3 transition-colors hover:text-accent hover:decoration-accent"
                  >
                    {{ session.title }}
                  </NuxtLink>
                  <span class="mt-0.5 block font-mono text-[0.625rem] leading-3 text-fg-3">{{ session.id }}</span>
                </td>
                <td>
                  <span class="inline-flex items-center gap-1.5">
                    <span class="ix-avatar ix-avatar-sm" aria-hidden="true">{{ agentInitials(session.agent) }}</span>
                    <span class="whitespace-nowrap text-xs text-fg-2">{{ session.agent }}</span>
                  </span>
                </td>
                <td class="font-mono text-xs tabular-nums">#{{ session.rank }}</td>
                <td>
                  <span class="flex items-center gap-2">
                    <MemoryScoreBar
                      :value="session.score"
                      :threshold="0.8"
                      :color="session.usage === 'injected' ? 'bg-memory' : session.usage === 'retrieved_only' ? 'bg-viz-2' : 'bg-fg-off'"
                      :label="`Composite ${session.score.toFixed(2)}`"
                      class="w-24"
                    />
                    <span class="font-mono text-xs text-fg-1 tabular-nums">{{ session.score.toFixed(2) }}</span>
                  </span>
                </td>
                <td><MemoryOutcomePill :usage="session.usage" /></td>
                <td>
                  <Tooltip :delay-duration="100">
                    <TooltipTrigger as-child>
                      <span class="cursor-default text-xs whitespace-nowrap text-fg-2">
                        {{ memoryRelativeTime(session.retrievedAt) }}
                      </span>
                    </TooltipTrigger>
                    <TooltipContent side="top" class="!font-mono !text-xs">{{ formatDayTimeUtc(session.retrievedAt) }}</TooltipContent>
                  </Tooltip>
                </td>
                <td class="w-8 text-right">
                  <button
                    type="button"
                    class="inline-flex size-6 items-center justify-center rounded text-fg-3 transition-colors hover:bg-raised hover:text-fg-1"
                    :aria-expanded="selected === session.id"
                    :aria-label="`Toggle details for ${session.title}`"
                    @click="toggle(session.id)"
                  >
                    <ChevronDown :size="13" :stroke-width="1.75" class="transition-transform" :class="selected === session.id && 'rotate-180'" aria-hidden="true" />
                  </button>
                </td>
              </tr>
              <tr v-if="selected === session.id" data-expanded-row>
                <td colspan="7" class="!h-auto bg-raised/40 py-3">
                  <div class="min-w-0 pl-2">
                    <dl class="flex flex-wrap gap-x-8 gap-y-1.5">
                      <div class="flex items-baseline gap-2">
                        <dt class="text-xs text-fg-3">Retrieved</dt>
                        <dd class="font-mono text-xs text-fg-2 tabular-nums">{{ formatDayTimeUtc(session.retrievedAt) }}</dd>
                      </div>
                      <div class="flex items-baseline gap-2">
                        <dt class="text-xs text-fg-3">Session outcome</dt>
                        <dd class="text-xs text-fg-1">{{ session.outcome }}</dd>
                      </div>
                      <div class="flex items-baseline gap-2">
                        <dt class="text-xs text-fg-3">Per-event components</dt>
                        <dd class="text-xs text-fg-2">
                          <MemoryEmptyValue /> <span class="text-fg-3">not stored</span>
                        </dd>
                      </div>
                    </dl>
                    <p class="mt-2 flex items-center gap-2 text-xs leading-4 text-fg-3">
                      <span>Linked answer evidence is not recorded.</span>
                      <NuxtLink
                        :to="`/sessions/${encodeURIComponent(session.id)}`"
                        class="inline-flex items-center gap-0.5 font-medium text-fg-2 underline decoration-line-strong underline-offset-3 transition-colors hover:text-accent hover:decoration-accent"
                      >
                        Open session
                        <ArrowUpRight :size="11" :stroke-width="1.75" aria-hidden="true" />
                      </NuxtLink>
                    </p>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <div v-else class="flex items-start gap-3 p-5 pt-0 text-fg-3">
        <SearchX :size="16" :stroke-width="1.75" class="mt-0.5 shrink-0" aria-hidden="true" />
        <p class="text-[0.8125rem] leading-5">
          <span class="block font-medium text-fg-2">No retrieval events recorded</span>
          <span class="inline-flex items-start gap-1.5 text-xs leading-4 text-fg-3">
            {{ retrieval.note }}
            <MemoryInfoHint label="About missing retrievals">
              <p class="font-medium text-fg-1">No events is not proof of no use</p>
              <p class="mt-1">
                Quarantined, deleted, and tombstoned records are excluded from retrieval entirely. Absence of recorded
                events does not prove the memory was never used.
              </p>
            </MemoryInfoHint>
          </span>
        </p>
      </div>
    </section>

    <section
      v-if="terms.length"
      aria-labelledby="usage-composite"
      class="rounded-lg border border-line-subtle bg-surface p-5"
    >
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="usage-composite" class="text-sm leading-5 font-semibold text-fg-1">Composite score breakdown</h2>
        <span class="flex items-center gap-1.5 text-xs text-fg-3">
          Record-level composite
          <span class="font-mono text-sm font-semibold text-fg-1 tabular-nums">{{ retrieval.avgComposite.toFixed(2) }}</span>
          <MemoryInfoHint label="About the composite score">
            <p class="font-medium text-fg-1">About this score</p>
            <p class="mt-1">
              The composite blends relevance, recency, usefulness, confidence, and frequency. It is not a retrieval
              similarity, and the inclusion threshold value is not recorded in this preview.
            </p>
          </MemoryInfoHint>
        </span>
      </div>

      <div class="mt-4 flex h-3.5 w-full overflow-hidden rounded-full bg-raised" aria-hidden="true">
        <span
          v-for="(entry, index) in contributions"
          :key="entry.term.key"
          class="h-full transition-[width] duration-300 ease-out first:rounded-l-full last:rounded-r-full"
          :style="segmentStyle(entry.term, index)"
        />
      </div>

      <dl class="mt-4 flex flex-col">
        <div
          v-for="entry in contributions"
          :key="entry.term.key"
          class="grid grid-cols-[minmax(10rem,16rem)_minmax(0,1fr)_3.5rem_4.5rem] items-center gap-4 border-b border-line-subtle py-2.5 last:border-0"
        >
          <dt class="min-w-0">
            <span class="flex items-center gap-2 text-[0.8125rem] leading-5 text-fg-1">
              <span class="size-2 shrink-0 rounded-full" :class="contributionColor(entry.term.key)" aria-hidden="true" />
              {{ entry.term.label }}
            </span>
            <span class="mt-0.5 block pl-4 text-xs leading-4 text-fg-3">{{ entry.term.note }}</span>
          </dt>
          <dd class="min-w-0">
            <MemoryScoreBar :value="entry.term.value" :color="contributionColor(entry.term.key)" :label="`${entry.term.label} score`" />
          </dd>
          <dd class="text-right font-mono text-xs text-fg-3 tabular-nums">×{{ entry.term.weight.toFixed(2) }}</dd>
          <dd class="text-right font-mono text-xs font-semibold text-fg-1 tabular-nums">{{ entry.contribution.toFixed(3) }}</dd>
        </div>
      </dl>
    </section>
  </div>
</template>
