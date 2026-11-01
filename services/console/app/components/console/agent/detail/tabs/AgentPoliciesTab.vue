<script setup lang="ts">
import { computed } from "vue"
import { Check, Minus, X } from "@lucide/vue"
import AgentVersionTag from "../../primitives/AgentVersionTag.vue"
import MemoryScoreBar from "@/components/console/memory/primitives/MemoryScoreBar.vue"
import { formatAgentMoney, formatAgentRelative } from "@/lib/agent-detail"
import type { AgentDetail, AgentPolicyRule } from "@/lib/agent-preview"

const props = defineProps<{ agent: AgentDetail }>()

const policy = computed(() => props.agent.policy)

const groupedRules = computed(() => {
  if (!policy.value) return []
  const groups = new Map<AgentPolicyRule["group"], AgentPolicyRule[]>()
  for (const rule of policy.value.rules) {
    const list = groups.get(rule.group) ?? []
    list.push(rule)
    groups.set(rule.group, list)
  }
  return [...groups.entries()]
})

const modeConfig = {
  enforce: { icon: Check, tone: "text-ok", word: "Enforce" },
  audit: { icon: Minus, tone: "text-warn", word: "Audit" },
  disabled: { icon: X, tone: "text-fg-3", word: "Disabled" },
} as const

const decisionConfig = {
  allow: { tone: "text-ok", mark: "✓", word: "allowed" },
  deny: { tone: "text-crit", mark: "✕", word: "blocked" },
  require_approval: { tone: "text-warn", mark: "⏸", word: "sent for approval" },
} as const
</script>

<template>
  <div class="min-w-0">
    <template v-if="policy">
      <div class="grid min-w-0 items-start gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(16rem,1fr)]">
        <div class="min-w-0 space-y-6">
          <section aria-labelledby="policy-capabilities">
            <h2 id="policy-capabilities" class="text-sm leading-5 font-semibold text-fg-1">What this agent can do</h2>
            <div class="mt-3 grid gap-3 md:grid-cols-3">
              <div class="rounded-lg border border-ok/25 bg-surface-1 p-4">
                <p class="flex items-center gap-1.5 text-xs font-semibold text-ok">
                  <Check :size="13" :stroke-width="2" aria-hidden="true" /> Can
                </p>
                <ul class="mt-2 flex flex-col gap-1.5 text-xs leading-4 text-fg-2 text-pretty">
                  <li v-for="item in policy.can" :key="item">{{ item }}</li>
                </ul>
              </div>
              <div class="rounded-lg border border-warn/25 bg-surface-1 p-4">
                <p class="flex items-center gap-1.5 text-xs font-semibold text-warn">
                  <Minus :size="13" :stroke-width="2" aria-hidden="true" /> Needs approval
                </p>
                <ul v-if="policy.approval.length" class="mt-2 flex flex-col gap-1.5 text-xs leading-4 text-fg-2 text-pretty">
                  <li v-for="item in policy.approval" :key="item">{{ item }}</li>
                </ul>
                <p v-else class="mt-2 text-xs text-fg-3">Nothing requires approval.</p>
              </div>
              <div class="rounded-lg border border-crit/25 bg-surface-1 p-4">
                <p class="flex items-center gap-1.5 text-xs font-semibold text-crit">
                  <X :size="13" :stroke-width="2" aria-hidden="true" /> Can't
                </p>
                <ul class="mt-2 flex flex-col gap-1.5 text-xs leading-4 text-fg-2 text-pretty">
                  <li v-for="item in policy.cannot" :key="item">{{ item }}</li>
                </ul>
              </div>
            </div>
            <p class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs text-fg-3 tabular-nums">
              <span class="text-ok">✓ {{ policy.decisions.allowed.toLocaleString("en-US") }} allowed</span>
              <span class="text-crit">✕ {{ policy.decisions.blocked.toLocaleString("en-US") }} blocked</span>
              <span class="text-warn">⏸ {{ policy.decisions.approval.toLocaleString("en-US") }} sent for approval</span>
              <span class="font-sans">(last 7 days)</span>
            </p>
          </section>

          <section
            v-if="policy.limit"
            aria-labelledby="policy-limit"
            class="rounded-lg border border-line-subtle bg-surface-1 p-4"
          >
            <h2 id="policy-limit" class="text-sm leading-5 font-semibold text-fg-1">{{ policy.limit.label }}</h2>
            <div class="mt-2 flex items-center gap-3">
              <MemoryScoreBar
                :value="policy.limit.valueUsd / policy.limit.limitUsd"
                color="bg-viz-2"
                :label="`${policy.limit.label}: ${formatAgentMoney(policy.limit.valueUsd)} of ${formatAgentMoney(policy.limit.limitUsd)}`"
                class="max-w-md"
              />
              <span class="font-mono text-xs text-fg-2 tabular-nums">
                {{ formatAgentMoney(policy.limit.valueUsd) }} of {{ formatAgentMoney(policy.limit.limitUsd) }}
              </span>
            </div>
            <p class="mt-1.5 text-[0.6875rem] leading-3.5 text-fg-3">
              This is a policy limit, not the agent's spend budget (Cost &amp; budgets tab).
            </p>
          </section>

          <section aria-labelledby="policy-rules">
            <h2 id="policy-rules" class="text-sm leading-5 font-semibold text-fg-1">Rules</h2>
            <div class="mt-2 overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
              <div class="overflow-x-auto">
                <table class="ix-table" aria-label="Policy rules">
                  <thead>
                    <tr>
                      <th scope="col" class="w-56">Rule</th>
                      <th scope="col" class="w-40">Value</th>
                      <th scope="col" class="w-24">Mode</th>
                      <th scope="col" class="w-28">Source</th>
                      <th scope="col" class="w-32">Last decision</th>
                      <th scope="col" class="w-32">Last changed</th>
                    </tr>
                  </thead>
                  <tbody>
                    <template v-for="[group, rules] in groupedRules" :key="group">
                      <tr class="group-header-row">
                        <td colspan="6" class="!h-8 bg-canvas !py-0 text-[0.6875rem] font-medium text-fg-2">{{ group }}</td>
                      </tr>
                      <tr v-for="rule in rules" :key="rule.id">
                        <td class="text-xs text-fg-1">{{ rule.rule }}</td>
                        <td class="font-mono text-xs text-fg-2">{{ rule.value }}</td>
                        <td>
                          <span class="inline-flex items-center gap-1.5 text-xs" :class="modeConfig[rule.mode].tone">
                            <component :is="modeConfig[rule.mode].icon" :size="11" :stroke-width="2" aria-hidden="true" />
                            {{ modeConfig[rule.mode].word }}
                          </span>
                        </td>
                        <td class="text-xs" :class="rule.source === 'Agent override' ? 'text-fg-1' : 'text-fg-3'">{{ rule.source }}</td>
                        <td class="text-xs text-fg-3">{{ rule.lastDecision }}</td>
                        <td class="text-xs text-fg-3" :title="`by ${rule.lastChangedBy}`">{{ formatAgentRelative(rule.lastChangedAt) }}</td>
                      </tr>
                    </template>
                  </tbody>
                </table>
              </div>
            </div>
            <p class="mt-2 text-xs leading-4 text-fg-3">
              Tool allow/deny lists live only in the MCP tools tab. Rule values come from the agent config; engine-backed
              decisions are pending the policy engine contract.
            </p>
          </section>
        </div>

        <aside class="min-w-0 space-y-4 xl:sticky xl:top-[6.5rem]" aria-label="Policy decisions">
          <section class="rounded-lg border border-line-subtle bg-surface-1 p-4" aria-labelledby="policy-recent">
            <h2 id="policy-recent" class="text-sm leading-5 font-semibold text-fg-1">Recent decisions</h2>
            <ul class="mt-2 flex flex-col divide-y divide-line-subtle">
              <li v-for="decision in policy.recent.slice(0, 10)" :key="decision.id" class="py-2">
                <p class="flex items-baseline gap-1.5 text-xs leading-4">
                  <span :class="decisionConfig[decision.decision].tone" aria-hidden="true">{{ decisionConfig[decision.decision].mark }}</span>
                  <span class="min-w-0 flex-1 text-fg-1">{{ decision.action }}</span>
                  <span class="shrink-0 text-fg-3">{{ formatAgentRelative(decision.at) }}</span>
                </p>
                <p class="mt-0.5 text-[0.6875rem] leading-3.5 text-fg-3">
                  {{ decision.value }} · decisive rule: {{ decision.rule }}
                  <template v-if="decision.runId"> · run {{ decision.runId }}</template>
                </p>
              </li>
            </ul>
            <p v-if="!policy.recent.length" class="mt-2 text-xs text-fg-3">No blocked or approval decisions recorded.</p>
          </section>

          <section class="rounded-lg border border-line-subtle bg-surface-1 p-4" aria-labelledby="policy-facts">
            <h2 id="policy-facts" class="text-[0.6875rem] font-semibold tracking-[0.08em] text-fg-3 uppercase">Policy</h2>
            <dl class="mt-2 flex flex-col gap-1.5 text-xs">
              <div class="flex items-baseline justify-between gap-3">
                <dt class="text-fg-3">Name</dt>
                <dd class="font-mono text-fg-2">{{ policy.name }}</dd>
              </div>
              <div class="flex items-baseline justify-between gap-3">
                <dt class="text-fg-3">Version</dt>
                <dd><AgentVersionTag label="Policy" :value="`v${policy.version}`" tone="default" /></dd>
              </div>
              <div class="flex items-baseline justify-between gap-3">
                <dt class="text-fg-3">Rules</dt>
                <dd class="font-mono text-fg-2 tabular-nums">{{ policy.rules.length }}</dd>
              </div>
            </dl>
          </section>
        </aside>
      </div>
    </template>

    <div v-else class="rounded-lg border border-dashed border-line px-5 py-8 text-center">
      <p class="text-sm font-medium text-fg-1">No policy is set</p>
      <p class="mt-1 text-xs leading-4 text-fg-3">Only org defaults apply.</p>
    </div>
  </div>
</template>

<style scoped>
.group-header-row:hover {
  background: transparent !important;
}
</style>
