<script setup lang="ts">
import { computed } from "vue"
import { ArrowRight, FlaskConical } from "@lucide/vue"
import {
  POLICY_EFFECT_LABELS,
  policyRuleHref,
  type PolicyImpact,
} from "@/lib/policy-preview"
import { formatGovernNumber, formatGovernStamp } from "@/lib/govern-format"
import GovernPendingData from "@/components/console/govern/primitives/GovernPendingData.vue"

const props = withDefaults(
  defineProps<{
    impact: PolicyImpact
    showByRule?: boolean
  }>(),
  { showByRule: true },
)

const changedPct = computed(() => (props.impact.replayed > 0 ? (props.impact.changed / props.impact.replayed) * 100 : 0))
</script>

<template>
  <GovernPendingData
    v-if="impact.status === 'not_run'"
    title="Impact simulation"
    contract="operator.policies.impact.v1"
    description="Replay prior decisions against this snapshot before publishing."
  />

  <section v-else class="rounded-lg border border-line-subtle bg-surface-1">
    <header class="flex flex-wrap items-center justify-between gap-2 border-b border-line-subtle px-4 py-2.5">
      <div class="flex items-center gap-2">
        <FlaskConical :size="14" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
        <div>
          <h3 class="text-sm font-semibold text-fg-1">Impact simulation</h3>
          <p class="mt-0.5 text-xs text-fg-3">
            Replayed {{ formatGovernNumber(impact.replayed) }} recorded decisions from
            {{ formatGovernStamp(impact.windowFrom) }} to {{ formatGovernStamp(impact.windowTo) }}.
          </p>
        </div>
      </div>
      <span
        class="inline-flex h-5.5 items-center rounded-full border px-2 text-xs font-medium"
        :class="impact.status === 'passed' ? 'border-transparent bg-transparent text-ok' : 'border-transparent bg-transparent text-warn'"
      >{{ impact.status === "passed" ? "Simulation passed" : "Simulation failed" }}</span>
    </header>

    <dl class="grid grid-cols-3 gap-px border-b border-line-subtle bg-line-subtle max-sm:grid-cols-1">
      <div class="bg-surface-1 px-4 py-3">
        <dt class="text-[0.6875rem] text-fg-3">Replayed decisions</dt>
        <dd class="mt-0.5 font-mono text-lg leading-6 text-fg-1 tabular-nums">{{ formatGovernNumber(impact.replayed) }}</dd>
      </div>
      <div class="bg-surface-1 px-4 py-3">
        <dt class="text-[0.6875rem] text-fg-3">Would change</dt>
        <dd class="mt-0.5 font-mono text-lg leading-6 tabular-nums" :class="impact.changed > 0 ? 'text-warn' : 'text-fg-1'">
          {{ formatGovernNumber(impact.changed) }}
          <span class="text-xs text-fg-3">({{ changedPct.toFixed(1) }}%)</span>
        </dd>
      </div>
      <div class="bg-surface-1 px-4 py-3">
        <dt class="text-[0.6875rem] text-fg-3">Unchanged</dt>
        <dd class="mt-0.5 font-mono text-lg leading-6 text-fg-1 tabular-nums">{{ formatGovernNumber(impact.unchanged) }}</dd>
      </div>
    </dl>

    <div class="grid gap-4 p-4 lg:grid-cols-2">
      <div>
        <p class="text-[0.6875rem] font-medium tracking-wide text-fg-3 uppercase">Decision transitions</p>
        <ul v-if="impact.transitions.length" class="mt-2 space-y-1.5">
          <li
            v-for="transition in impact.transitions"
            :key="`${transition.from}-${transition.to}`"
            class="flex items-center justify-between gap-2 rounded-lg border border-line-subtle bg-surface-2/60 px-2.5 py-1.5 text-xs"
          >
            <span class="flex min-w-0 items-center gap-1.5">
              <span class="text-fg-2">{{ POLICY_EFFECT_LABELS[transition.from] }}</span>
              <ArrowRight :size="11" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
              <span class="font-medium text-fg-1">{{ POLICY_EFFECT_LABELS[transition.to] }}</span>
            </span>
            <span class="font-mono text-fg-1 tabular-nums">{{ formatGovernNumber(transition.count) }}</span>
          </li>
        </ul>
        <p v-else class="mt-2 text-xs text-fg-3">No decision would change.</p>
      </div>

      <div v-if="showByRule">
        <p class="text-[0.6875rem] font-medium tracking-wide text-fg-3 uppercase">Rules that move decisions</p>
        <ul v-if="impact.byRule.length" class="mt-2 space-y-1.5">
          <li
            v-for="rule in impact.byRule"
            :key="rule.ruleId"
            class="flex items-center justify-between gap-2 rounded-lg border border-line-subtle bg-surface-2/60 px-2.5 py-1.5 text-xs"
          >
            <NuxtLink :to="policyRuleHref(rule.ruleId)" class="ix-link min-w-0 truncate">{{ rule.label }}</NuxtLink>
            <span class="shrink-0 font-mono text-fg-2 tabular-nums">
              {{ formatGovernNumber(rule.changed) }} of {{ formatGovernNumber(rule.fired) }}
            </span>
          </li>
        </ul>
        <p v-else class="mt-2 text-xs text-fg-3">No rule would change a decision.</p>
      </div>
    </div>

    <p class="border-t border-line-subtle px-4 py-2 text-[0.6875rem] leading-4 text-fg-3">
      This is a replay of recorded decisions, not a forecast of production traffic. Counts come from the policy
      simulation endpoint.
    </p>
  </section>
</template>
