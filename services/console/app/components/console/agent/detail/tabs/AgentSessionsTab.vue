<script setup lang="ts">
import { computed } from "vue"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useAgentTabQueryString } from "@/composables/useAgentTabQuery"
import { formatAgentMoney, formatAgentRelative, formatAgentStamp, formatAgentTokens } from "@/lib/agent-detail"
import type { AgentDetail } from "@/lib/agent-preview"

const props = defineProps<{ agent: AgentDetail }>()

const outcomeFilter = useAgentTabQueryString("soutcome")

const liveSessions = computed(() => props.agent.sessionsData.filter((session) => session.live))
const filtered = computed(() =>
  outcomeFilter.value === "all"
    ? props.agent.sessionsData
    : props.agent.sessionsData.filter((session) =>
        outcomeFilter.value === "failed" ? session.failures > 0 || session.outcome === "failed" : session.failures === 0 && session.outcome !== "failed",
      ),
)

function durationLabel(ms: number): string {
  return ms < 90_000 ? `${Math.round(ms / 1000)}s` : `${Math.round(ms / 60_000)}m`
}
</script>

<template>
  <div class="min-w-0 space-y-5">
    <section v-if="liveSessions.length" aria-labelledby="agent-live-sessions">
      <h2 id="agent-live-sessions" class="text-sm leading-5 font-semibold text-fg-1">Live now</h2>
      <div class="mt-2 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <div
          v-for="session in liveSessions"
          :key="session.id"
          class="min-w-0 rounded-lg border border-line-subtle bg-surface-1 p-4"
        >
          <p class="flex items-center gap-2">
            <span class="size-1.5 animate-pulse rounded-full bg-ok" aria-hidden="true" />
            <NuxtLink
              :to="`/sessions/${encodeURIComponent(session.id)}`"
              class="min-w-0 flex-1 truncate font-mono text-xs text-fg-1 underline decoration-transparent underline-offset-3 hover:text-accent-memory hover:decoration-accent-memory"
            >
              {{ session.id }}
            </NuxtLink>
          </p>
          <dl class="mt-2 flex flex-col gap-1 text-xs">
            <div class="flex justify-between gap-2">
              <dt class="text-fg-3">Started</dt>
              <dd class="font-mono text-fg-2" :title="formatAgentStamp(session.startedAt)">{{ formatAgentRelative(session.startedAt) }}</dd>
            </div>
            <div class="flex justify-between gap-2">
              <dt class="text-fg-3">Turns so far</dt>
              <dd class="font-mono text-fg-2 tabular-nums">{{ session.turns }}</dd>
            </div>
            <div class="flex justify-between gap-2">
              <dt class="text-fg-3">Current step</dt>
              <dd class="min-w-0 truncate text-right text-fg-2">{{ session.currentStep ?? "—" }}</dd>
            </div>
          </dl>
        </div>
      </div>
    </section>

    <div class="flex flex-wrap items-center gap-2">
      <div class="flex items-center rounded-lg border border-line-subtle bg-surface-1 p-0.5" role="group" aria-label="Filter sessions by outcome">
        <button
          v-for="option in ['all', 'succeeded', 'failed'] as const"
          :key="option"
          type="button"
          class="inline-flex h-7 items-center rounded-md px-2.5 text-xs font-medium capitalize transition-colors"
          :class="outcomeFilter === option ? 'bg-surface-2 text-fg-1 outline outline-1 outline-line-strong' : 'text-fg-3 hover:text-fg-1'"
          @click="outcomeFilter = option"
        >
          {{ option }}
        </button>
      </div>
      <span class="ml-auto text-xs text-fg-3">{{ filtered.length }} sessions</span>
    </div>

    <div class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
      <div class="overflow-x-auto">
        <table class="ix-table" aria-label="Agent sessions">
          <thead>
            <tr>
              <th scope="col" class="w-40">Session</th>
              <th scope="col" class="w-28">Started</th>
              <th scope="col" class="w-20">Duration</th>
              <th scope="col" class="w-16 text-right">Turns</th>
              <th scope="col" class="w-32">Outcome</th>
              <th scope="col" class="w-24">Drift</th>
              <th scope="col" class="w-40">Tokens</th>
              <th scope="col" class="w-20 text-right">Cost</th>
              <th scope="col" class="w-24 text-right">Memories</th>
              <th scope="col" class="w-28">End user</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="session in filtered" :key="session.id">
              <td>
                <NuxtLink
                  :to="`/sessions/${encodeURIComponent(session.id)}`"
                  class="font-mono text-xs text-fg-1 underline decoration-transparent underline-offset-3 transition-colors hover:text-accent-memory hover:decoration-accent-memory"
                >
                  {{ session.id }}
                </NuxtLink>
              </td>
              <td>
                <Tooltip :delay-duration="150">
                  <TooltipTrigger as-child>
                    <span class="cursor-default text-xs whitespace-nowrap text-fg-2">{{ formatAgentRelative(session.startedAt) }}</span>
                  </TooltipTrigger>
                  <TooltipContent side="top" class="!font-mono !text-xs">{{ formatAgentStamp(session.startedAt) }}</TooltipContent>
                </Tooltip>
              </td>
              <td class="font-mono text-xs text-fg-2 tabular-nums">{{ durationLabel(session.durationMs) }}</td>
              <td class="text-right font-mono text-xs text-fg-1 tabular-nums">{{ session.turns }}</td>
              <td>
                <span class="text-xs" :class="session.failures ? 'text-crit' : 'text-ok'">
                  {{ session.failures ? `${session.failures} failed` : session.outcome }}
                </span>
              </td>
              <td>
                <span v-if="session.driftAdvisories" class="text-xs text-warn">⚠ {{ session.driftAdvisories }}</span>
                <span v-else class="text-xs text-fg-off">—</span>
              </td>
              <td class="font-mono text-[0.6875rem] text-fg-3 tabular-nums">{{ formatAgentTokens(session.tokensIn, session.tokensOut) }}</td>
              <td class="text-right font-mono text-xs text-fg-1 tabular-nums">{{ formatAgentMoney(session.costUsd) }}</td>
              <td class="text-right font-mono text-xs text-fg-1 tabular-nums">{{ session.memoriesWritten }}</td>
              <td class="truncate text-xs text-fg-3">{{ session.endUser ?? "—" }}</td>
            </tr>
            <tr v-if="!filtered.length">
              <td colspan="10" class="!h-24 text-center text-xs text-fg-3">
                {{ agent.stats.lastRun === null && !agent.sessionsData.length ? "This agent has never started a session." : "No sessions match this filter." }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
