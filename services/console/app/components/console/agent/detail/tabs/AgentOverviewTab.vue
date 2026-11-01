<script setup lang="ts">
import { computed } from "vue"
import { ArrowUpRight, CircleSlash } from "@lucide/vue"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import AgentAttentionItem from "../../primitives/AgentAttentionItem.vue"
import AgentPendingData from "../../primitives/AgentPendingData.vue"
import AgentVersionTag from "../../primitives/AgentVersionTag.vue"
import MemoryJsonView from "@/components/console/memory/primitives/MemoryJsonView.vue"
import MemoryInfoHint from "@/components/console/memory/primitives/MemoryInfoHint.vue"
import {
  agentAttentionHref,
  formatAgentCount,
  formatAgentDate,
  formatAgentRelative,
  formatAgentStamp,
} from "@/lib/agent-detail"
import { agentProviderLabel, type AgentDetail, type AgentTab } from "@/lib/agent-preview"
import BrandIcon from "@/components/console/BrandIcon.vue"

const props = defineProps<{ agent: AgentDetail }>()
const emit = defineEmits<{ tab: [tab: AgentTab] }>()

const recentRuns = computed(() => props.agent.runsData.slice(0, 8))
const quarantinedMemories = computed(() => props.agent.memoriesData.filter((memory) => memory.quarantined))

// Recent activity: merged mini-timeline from audit, memories, directives.
const recentActivity = computed(() => {
  const events: { id: string; at: string; label: string; detail: string; tab: AgentTab }[] = []

  for (const event of props.agent.auditData.slice(0, 6)) {
    events.push({
      id: event.id,
      at: event.at,
      label: `${event.actor} · ${event.operation}`,
      detail: event.summary,
      tab: event.tab,
    })
  }

  for (const memory of quarantinedMemories.value.slice(0, 3)) {
    events.push({
      id: `mem-${memory.id}`,
      at: memory.lastUsedAt ?? props.agent.updatedAt,
      label: "Memory quarantined",
      detail: memory.preview.slice(0, 90),
      tab: "memories",
    })
  }

  if (props.agent.directive) {
    events.push({
      id: "directive-current",
      at: props.agent.directive.effectiveSince,
      label: `Directive v${props.agent.directive.version} activated`,
      detail:
        props.agent.directive.versions.find((version) => version.version === props.agent.directive?.version)?.summary ?? "",
      tab: "directives",
    })
  }

  return events.sort((first, second) => Date.parse(second.at) - Date.parse(first.at)).slice(0, 6)
})

const identityRows = computed(() => [
  { label: "ID", value: props.agent.id },
  { label: "Org", value: props.agent.org },
  { label: "Slug", value: props.agent.slug },
  { label: "Owner", value: props.agent.owner },
  { label: "Created by", value: props.agent.createdBy },
  { label: "Created", value: `${formatAgentDate(props.agent.createdAt)}` },
  { label: "Updated", value: formatAgentRelative(props.agent.updatedAt) },
])

const runsOnRows = computed(() => [
  { label: "Agent version", value: `v${props.agent.agentVersion}` },
  { label: "Model", value: props.agent.model },
  { label: "Provider", value: agentProviderLabel(props.agent.provider) },
  { label: "Environment", value: props.agent.env },
  { label: "Allowed providers", value: props.agent.allowedProviders.map(agentProviderLabel).join(", ") || "—" },
])

const memoryRows = computed(() => [
  { label: "Scope", value: props.agent.memoryScope },
  { label: "Extraction", value: props.agent.extractionEnabled ? "On" : "Off" },
  { label: "Max per context", value: String(props.agent.maxMemoriesPerContext) },
  { label: "Context budget", value: `${formatAgentCount(props.agent.contextBudgetTokens)} tokens` },
])

const safetyRows = computed(() => [
  { label: "Drift detection", value: `On · sensitivity ${props.agent.driftSensitivity.toFixed(2)}` },
  { label: "Loop detection", value: `≥ ${props.agent.loopDetectionThreshold} iterations` },
  { label: "Heartbeat", value: `${props.agent.heartbeatSeconds}s` },
])
</script>

<template>
  <div class="grid min-w-0 items-start gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(18rem,1fr)]">
    <div class="min-w-0 space-y-6">
      <section aria-labelledby="agent-attention">
        <h2 id="agent-attention" class="sr-only">Needs attention</h2>
        <ul v-if="agent.attention.length" class="flex flex-col gap-2 rounded-lg border border-line-subtle bg-surface p-4">
          <li v-for="item in agent.attention" :key="item.id">
            <AgentAttentionItem :item="item" :show-agent="false" :href="agentAttentionHref({ agentId: agent.id, tab: item.tab, filter: item.filter })" />
          </li>
        </ul>
        <p v-else class="text-sm font-medium text-ok">✓ Nothing needs attention</p>
      </section>

      <section aria-labelledby="agent-recent-runs">
        <h2 id="agent-recent-runs" class="text-sm leading-5 font-semibold text-fg-1">Recent runs</h2>
        <div class="mt-2">
          <AgentPendingData
            title="Run outcome history"
            contract="GET /v1/agents/{id}/stats"
            description="Per-day succeeded/failed counts will draw the outcome chart."
            class="!mb-3"
          />
        </div>
        <ul v-if="recentRuns.length" class="divide-y divide-line-subtle rounded-lg border border-line-subtle bg-surface-1">
          <li v-for="run in recentRuns" :key="run.id" class="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5">
            <CircleSlash v-if="run.status === 'failed'" :size="13" :stroke-width="2" class="shrink-0 text-crit" aria-hidden="true" />
            <span v-else class="size-2 shrink-0 rounded-full bg-ok" aria-hidden="true" />
            <NuxtLink
              :to="`/sessions/${encodeURIComponent(run.sessionId)}`"
              class="min-w-0 flex-1 truncate font-mono text-xs text-fg-2 underline decoration-transparent underline-offset-3 transition-colors hover:text-accent-memory hover:decoration-accent-memory"
            >
              {{ run.id }}
            </NuxtLink>
            <span class="shrink-0 font-mono text-[0.6875rem] text-fg-3 tabular-nums">
              {{ formatAgentCount(run.tokensIn) }} in · {{ (run.durationMs / 1000).toFixed(1) }}s
            </span>
            <Tooltip :delay-duration="150">
              <TooltipTrigger as-child>
                <span class="shrink-0 text-[0.6875rem] text-fg-3">{{ formatAgentRelative(run.startedAt) }}</span>
              </TooltipTrigger>
              <TooltipContent side="top" class="!font-mono !text-xs">{{ formatAgentStamp(run.startedAt) }}</TooltipContent>
            </Tooltip>
          </li>
        </ul>
        <p v-else class="rounded-lg border border-dashed border-line px-4 py-3 text-xs text-fg-3">This agent hasn't run yet.</p>
        <button type="button" class="mt-2 inline-flex items-center gap-1 text-xs font-medium text-fg-2 transition-colors hover:text-accent-memory" @click="emit('tab', 'runs')">
          View all runs
          <ArrowUpRight :size="11" :stroke-width="1.9" aria-hidden="true" />
        </button>
      </section>

      <section aria-labelledby="agent-recent-activity">
        <h2 id="agent-recent-activity" class="text-sm leading-5 font-semibold text-fg-1">Recent activity</h2>
        <ol v-if="recentActivity.length" class="mt-3 border-l border-line-subtle pl-4">
          <li v-for="event in recentActivity" :key="event.id" class="relative pb-4 last:pb-0">
            <span class="absolute top-1.5 -left-[1.1875rem] size-2 rounded-full border border-line-strong bg-surface-1" aria-hidden="true" />
            <button type="button" class="text-left text-xs leading-4 font-medium text-fg-2 transition-colors hover:text-accent-memory" @click="emit('tab', event.tab)">
              {{ event.label }}
            </button>
            <p class="mt-0.5 line-clamp-1 text-xs leading-4 text-fg-3">{{ event.detail }}</p>
            <p class="mt-0.5 font-mono text-[0.625rem] text-fg-3" :title="formatAgentStamp(event.at)">{{ formatAgentRelative(event.at) }}</p>
          </li>
        </ol>
        <p v-else class="mt-2 text-xs text-fg-3">No recorded activity.</p>
      </section>

      <details class="group rounded-lg border border-line-subtle bg-surface-1">
        <summary class="flex cursor-pointer list-none items-center justify-between p-4 text-sm font-semibold text-fg-1 [&::-webkit-details-marker]:hidden">
          Raw record
          <span class="text-xs font-normal text-fg-3 group-open:hidden">Show</span>
          <span class="hidden text-xs font-normal text-fg-3 group-open:inline">Hide</span>
        </summary>
        <div class="border-t border-line-subtle p-4">
          <MemoryJsonView :value="agent.raw" />
        </div>
      </details>
    </div>

    <aside class="min-w-0 space-y-4 xl:sticky xl:top-[6.5rem]" aria-label="Agent facts">
      <section class="rounded-lg border border-line-subtle bg-surface-1 p-4" aria-labelledby="agent-facts-identity">
        <h2 id="agent-facts-identity" class="text-[0.6875rem] font-semibold tracking-[0.08em] text-fg-3 uppercase">Identity</h2>
        <dl class="mt-2 flex flex-col gap-1.5">
          <div v-for="row in identityRows" :key="row.label" class="flex items-baseline justify-between gap-3 text-xs">
            <dt class="shrink-0 text-fg-3">{{ row.label }}</dt>
            <dd class="min-w-0 truncate text-right font-mono text-fg-2" :title="row.value">{{ row.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="rounded-lg border border-line-subtle bg-surface-1 p-4" aria-labelledby="agent-facts-runs">
        <h2 id="agent-facts-runs" class="flex items-center gap-1.5 text-[0.6875rem] font-semibold tracking-[0.08em] text-fg-3 uppercase">
          <BrandIcon :id="agent.provider" :size="13" :label="`${agentProviderLabel(agent.provider)} logo`" />
          Runs on
        </h2>
        <dl class="mt-2 flex flex-col gap-1.5">
          <div v-for="row in runsOnRows" :key="row.label" class="flex items-baseline justify-between gap-3 text-xs">
            <dt class="shrink-0 text-fg-3">{{ row.label }}</dt>
            <dd class="min-w-0 truncate text-right font-mono text-fg-2" :title="row.value">{{ row.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="rounded-lg border border-line-subtle bg-surface-1 p-4" aria-labelledby="agent-facts-governed">
        <h2 id="agent-facts-governed" class="text-[0.6875rem] font-semibold tracking-[0.08em] text-fg-3 uppercase">Governed by</h2>
        <div class="mt-2 flex flex-col gap-2 text-xs">
          <div v-if="agent.directive" class="flex items-center justify-between gap-2">
            <button
              type="button"
              class="min-w-0 truncate text-left text-xs text-fg-2 underline decoration-line-strong underline-offset-3 hover:text-fg-1"
              @click="emit('tab', 'directives')"
            >
              {{ agent.directive.name }}
            </button>
            <span class="flex shrink-0 items-center gap-1">
              <AgentVersionTag label="Directive" :value="`v${agent.directive.version}`" />
              <MemoryInfoHint label="What is a directive?">
                A directive is the instruction text the agent follows. Not a policy.
              </MemoryInfoHint>
            </span>
          </div>
          <p v-else class="text-fg-3">No directive set.</p>
          <div v-if="agent.policy" class="flex items-center justify-between gap-2">
            <button
              type="button"
              class="min-w-0 truncate text-left font-mono text-xs text-fg-2 underline decoration-line-strong underline-offset-3 hover:text-fg-1"
              @click="emit('tab', 'policies')"
            >
              {{ agent.policy.name }}
            </button>
            <span class="flex shrink-0 items-center gap-1">
              <AgentVersionTag label="Policy" :value="`v${agent.policy.version}`" />
              <MemoryInfoHint label="What is a policy?">
                A policy is the set of rules that allow or block the agent's actions. Not a directive.
              </MemoryInfoHint>
            </span>
          </div>
          <p v-else class="text-fg-3">No policy set; org defaults apply.</p>
        </div>
      </section>

      <section class="rounded-lg border border-line-subtle bg-surface-1 p-4" aria-labelledby="agent-facts-memory">
        <h2 id="agent-facts-memory" class="text-[0.6875rem] font-semibold tracking-[0.08em] text-fg-3 uppercase">Memory</h2>
        <dl class="mt-2 flex flex-col gap-1.5">
          <div v-for="row in memoryRows" :key="row.label" class="flex items-baseline justify-between gap-3 text-xs">
            <dt class="shrink-0 text-fg-3">{{ row.label }}</dt>
            <dd class="min-w-0 truncate text-right font-mono text-fg-2" :title="row.value">{{ row.value }}</dd>
          </div>
        </dl>
        <button type="button" class="mt-2 text-xs font-medium text-fg-2 underline decoration-line-strong underline-offset-3 hover:text-fg-1" @click="emit('tab', 'memories')">
          Memories ›
        </button>
      </section>

      <section class="rounded-lg border border-line-subtle bg-surface-1 p-4" aria-labelledby="agent-facts-safety">
        <h2 id="agent-facts-safety" class="text-[0.6875rem] font-semibold tracking-[0.08em] text-fg-3 uppercase">Safety</h2>
        <dl class="mt-2 flex flex-col gap-1.5">
          <div v-for="row in safetyRows" :key="row.label" class="flex items-baseline justify-between gap-3 text-xs">
            <dt class="shrink-0 text-fg-3">{{ row.label }}</dt>
            <dd class="min-w-0 truncate text-right font-mono text-fg-2" :title="row.value">{{ row.value }}</dd>
          </div>
        </dl>
        <button type="button" class="mt-2 text-xs font-medium text-fg-2 underline decoration-line-strong underline-offset-3 hover:text-fg-1" @click="emit('tab', 'policies')">
          Rules in Policies ›
        </button>
      </section>
    </aside>
  </div>
</template>
