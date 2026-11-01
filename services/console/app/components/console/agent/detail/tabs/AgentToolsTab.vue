<script setup lang="ts">
import { computed, ref } from "vue"
import { Check, ChevronDown, Minus, X } from "@lucide/vue"
import AgentMetricCell from "../../primitives/AgentMetricCell.vue"
import { formatAgentCount, formatAgentDuration, formatAgentRelative, formatAgentStamp } from "@/lib/agent-detail"
import type { AgentDetail, AgentTool } from "@/lib/agent-preview"

const props = defineProps<{ agent: AgentDetail }>()

const expanded = ref<string | null>(null)

const servers = computed(() => {
  const map = new Map<string, { name: string; status: AgentTool["serverStatus"]; tools: number }>()
  for (const tool of props.agent.toolsData) {
    const entry = map.get(tool.server) ?? { name: tool.server, status: tool.serverStatus, tools: 0 }
    entry.tools += 1
    if (tool.serverStatus === "offline") entry.status = "offline"
    else if (tool.serverStatus === "degraded" && entry.status !== "offline") entry.status = "degraded"
    map.set(tool.server, entry)
  }
  return [...map.values()]
})

const ACCESS_CONFIG = {
  allowed: { icon: Check, tone: "text-ok", word: "Allowed" },
  denied: { icon: X, tone: "text-crit", word: "Denied" },
  approval: { icon: Minus, tone: "text-warn", word: "Needs approval" },
} as const

const SERVER_TONE: Record<AgentTool["serverStatus"], string> = {
  connected: "bg-ok",
  degraded: "bg-warn",
  offline: "bg-crit",
}

const statsMissing = (tool: AgentTool): boolean => tool.calls === null && tool.errorRate === null && tool.p95Ms === null
</script>

<template>
  <div class="min-w-0 space-y-5">
    <div class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
      <div class="overflow-x-auto">
        <table class="ix-table" aria-label="MCP tools">
          <thead>
            <tr>
              <th scope="col" class="w-48">Tool</th>
              <th scope="col" class="w-40">Server</th>
              <th scope="col" class="w-32">Access</th>
              <th scope="col" class="w-20 text-right">Calls</th>
              <th scope="col" class="w-24 text-right">Errors</th>
              <th scope="col" class="w-24 text-right">Retries</th>
              <th scope="col" class="w-20 text-right">p95</th>
              <th scope="col" class="w-28">Last called</th>
              <th scope="col" class="w-8"><span class="sr-only">Expand</span></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="tool in agent.toolsData" :key="tool.name">
              <tr :class="(tool.errorRate ?? 0) > 3 && tool.access !== 'denied' ? 'tool-problem' : ''">
                <td class="font-mono text-xs font-medium text-fg-1">{{ tool.name }}</td>
                <td>
                  <span class="inline-flex items-center gap-1.5 text-xs text-fg-2">
                    <span class="size-1.5 rounded-full" :class="SERVER_TONE[tool.serverStatus]" aria-hidden="true" />
                    {{ tool.server }}
                  </span>
                </td>
                <td>
                  <span class="inline-flex items-center gap-1.5 text-xs" :class="ACCESS_CONFIG[tool.access].tone">
                    <component :is="ACCESS_CONFIG[tool.access].icon" :size="11" :stroke-width="2" aria-hidden="true" />
                    {{ ACCESS_CONFIG[tool.access].word }}
                  </span>
                </td>
                <template v-if="!statsMissing(tool)">
                  <td class="text-right font-mono text-xs text-fg-1 tabular-nums">{{ formatAgentCount(tool.calls) }}</td>
                  <td>
                    <AgentMetricCell :value="tool.errorRate === null ? '—' : `${tool.errorRate.toFixed(1)}%`" :over="(tool.errorRate ?? 0) > 3" threshold="Band: ≤ 3.0%" />
                  </td>
                  <td class="text-right font-mono text-xs text-fg-2 tabular-nums">{{ tool.retriesPerCall === null ? "—" : tool.retriesPerCall.toFixed(1) }}</td>
                  <td class="text-right font-mono text-xs text-fg-1 tabular-nums">{{ tool.p95Ms === null ? "—" : formatAgentDuration(tool.p95Ms) }}</td>
                  <td>
                    <span v-if="tool.lastCalledAt" class="text-xs whitespace-nowrap text-fg-2" :title="formatAgentStamp(tool.lastCalledAt)">{{ formatAgentRelative(tool.lastCalledAt) }}</span>
                    <span v-else class="text-xs text-fg-3">never</span>
                  </td>
                </template>
                <td v-if="statsMissing(tool)" colspan="5" class="text-xs text-fg-3">
                  Not reported yet · needs the tool stats contract
                </td>
                <td class="text-right">
                  <button
                    type="button"
                    class="inline-flex size-6 items-center justify-center rounded text-fg-3 transition-colors hover:bg-raised hover:text-fg-1"
                    :aria-expanded="expanded === tool.name"
                    :aria-label="`Toggle details for ${tool.name}`"
                    @click="expanded = expanded === tool.name ? null : tool.name"
                  >
                    <ChevronDown :size="13" :stroke-width="1.9" class="transition-transform" :class="expanded === tool.name && 'rotate-180'" aria-hidden="true" />
                  </button>
                </td>
              </tr>
              <tr v-if="expanded === tool.name">
                <td colspan="9" class="!h-auto bg-raised/40 !py-3">
                  <div class="min-w-0 pl-2">
                    <p class="text-xs leading-4 text-fg-2 text-pretty">{{ tool.description }}</p>
                    <p class="mt-3 text-[0.6875rem] font-semibold tracking-[0.06em] text-fg-3 uppercase">Last calls</p>
                    <ul class="mt-1.5 flex flex-col gap-1">
                      <li v-for="call in tool.sampleCalls.slice(0, 5)" :key="call.at" class="flex items-center gap-3 text-xs">
                        <span :class="call.outcome === 'failed' ? 'text-crit' : 'text-ok'" aria-hidden="true">{{ call.outcome === "failed" ? "✕" : "✓" }}</span>
                        <span class="font-mono text-fg-3" :title="formatAgentStamp(call.at)">{{ formatAgentRelative(call.at) }}</span>
                        <span class="font-mono text-fg-3 tabular-nums">{{ call.durationMs }} ms</span>
                        <span class="font-mono text-fg-3">run {{ call.runId }}</span>
                      </li>
                    </ul>
                    <p class="mt-3 text-[0.6875rem] leading-3.5 text-fg-3">
                      Sample payloads are redacted by default; a privileged reveal is required.
                    </p>
                  </div>
                </td>
              </tr>
            </template>
            <tr v-if="!agent.toolsData.length">
              <td colspan="9" class="!h-24 text-center text-xs text-fg-3">No MCP tools are attached to this agent.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <section aria-labelledby="tools-servers">
      <h2 id="tools-servers" class="text-sm leading-5 font-semibold text-fg-1">Servers</h2>
      <ul class="mt-2 grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
        <li
          v-for="server in servers"
          :key="server.name"
          class="rounded-lg border border-line-subtle bg-surface-1 p-4"
        >
          <p class="flex items-center gap-2 text-xs">
            <span class="size-1.5 rounded-full" :class="SERVER_TONE[server.status]" aria-hidden="true" />
            <span class="min-w-0 flex-1 truncate font-mono font-medium text-fg-1">{{ server.name }}</span>
          </p>
          <p class="mt-1 text-xs text-fg-3">
            {{ server.status }} · {{ server.tools }} {{ server.tools === 1 ? "tool" : "tools" }}
          </p>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.tool-problem {
  box-shadow: inset 3px 0 0 var(--row-attention-edge);
}
</style>
