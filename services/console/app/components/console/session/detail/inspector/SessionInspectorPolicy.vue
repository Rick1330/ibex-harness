<script setup lang="ts">
import { computed } from "vue"
import { ArrowRight, ArrowUpRight, Check, Lock, Minus, X } from "@lucide/vue"
import type { SessionPolicyCheck, SessionPolicyPermission, SessionRound } from "@/lib/session-preview"
import MemoryInfoHint from "@/components/console/memory/primitives/MemoryInfoHint.vue"
import SessionCaveat from "../primitives/SessionCaveat.vue"
import SessionDecisionPill from "../primitives/SessionDecisionPill.vue"
import SessionRawRecord from "../primitives/SessionRawRecord.vue"
import SessionSectionLabel from "../primitives/SessionSectionLabel.vue"
import SessionThresholdBar from "../primitives/SessionThresholdBar.vue"

const props = defineProps<{
  round: SessionRound
}>()

const emit = defineEmits<{
  span: [label: string]
}>()

const policy = computed(() => props.round.policy)

const passed = computed(() => policy.value.checks.filter((check) => check.result === "pass").length)
const failed = computed(() => policy.value.checks.filter((check) => check.result === "fail").length)
const checksLabel = computed(() => {
  if (failed.value > 0) return `Checks · ${failed.value} failed`
  return `Checks · ${passed.value} passed`
})

const budgetNumbers = computed(() => {
  const numbers = policy.value.budgetDetail.match(/\d[\d,]*/g)?.map((value) => Number(value.replaceAll(",", ""))) ?? []
  const percentFromNumbers =
    numbers.length >= 2 && numbers[1]! > 0 ? Math.round((numbers[0]! / numbers[1]!) * 100) : null
  const percentFromLabel = Number(policy.value.budget.match(/(\d+)%/)?.[1] ?? Number.NaN)
  const percent = Number.isFinite(percentFromLabel) ? percentFromLabel : percentFromNumbers
  return { numbers, percent }
})

function checkIcon(check: SessionPolicyCheck) {
  if (check.result === "pass") return Check
  if (check.result === "fail") return X
  return Minus
}

function checkTone(check: SessionPolicyCheck): string {
  if (check.result === "pass") return "text-ok"
  if (check.result === "fail") return "text-crit"
  return "text-fg-3"
}

function permissionIcon(permission: SessionPolicyPermission) {
  if (permission.tone === "allow") return Check
  if (permission.tone === "deny") return X
  return Lock
}

function permissionTone(permission: SessionPolicyPermission): string {
  if (permission.tone === "allow") return "text-ok"
  if (permission.tone === "deny") return "text-crit"
  return "text-fg-2"
}
</script>

<template>
  <div class="space-y-5">
    <div class="flex justify-end">
      <MemoryInfoHint label="What is a policy?">
        A policy decides which actions the agent is allowed to take for this turn. The directive, in the previous tab,
        is the instruction the agent was given.
      </MemoryInfoHint>
    </div>

    <section>
      <div class="flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <SessionDecisionPill :decision="policy.decision" />
        <NuxtLink
          to="/policies"
          class="ml-auto inline-flex items-center gap-1 font-mono text-[0.6875rem] leading-4 text-fg-2 underline-offset-4 hover:text-fg-1 hover:underline"
        >
          {{ policy.id }}
          <ArrowUpRight :size="10" :stroke-width="1.75" aria-hidden="true" />
        </NuxtLink>
      </div>
      <p class="mt-1.5 flex flex-wrap items-center gap-x-1.5 text-xs leading-4 text-fg-3">
        <span>Action <span class="font-mono text-fg-2">{{ policy.action }}</span></span>
        <span aria-hidden="true">·</span>
        <span>evaluated in <span class="font-mono tabular-nums">{{ policy.evaluatedInMs }} ms</span></span>
        <button type="button" class="ix-inline-link" @click="emit('span', 'policy.check')">
          Show in trace
          <ArrowRight :size="11" :stroke-width="1.75" aria-hidden="true" />
        </button>
      </p>
    </section>

    <section class="ix-rule">
      <SessionSectionLabel>Decisive rule</SessionSectionLabel>
      <p class="mt-1 text-sm leading-5 text-fg-1 text-pretty">{{ policy.rule }}</p>
      <SessionThresholdBar
        v-if="policy.threshold"
        class="mt-3"
        :value="policy.threshold.value"
        :limit="policy.threshold.limit"
        :value-label="policy.threshold.valueLabel"
        :limit-label="policy.threshold.limitLabel"
        label="Checked value against the rule limit"
      />
    </section>

    <section>
      <SessionSectionLabel>{{ checksLabel }}</SessionSectionLabel>
      <ul class="mt-1 divide-y divide-line-subtle">
        <li v-for="check in policy.checks" :key="check.label" class="flex items-start gap-2 py-2">
          <component :is="checkIcon(check)" :size="13" :stroke-width="2.2" class="mt-0.5 shrink-0" :class="checkTone(check)" aria-hidden="true" />
          <span class="min-w-0 flex-1">
            <span class="flex flex-wrap items-baseline gap-x-1.5">
              <span class="text-[0.8125rem] leading-5 font-medium text-fg-1">{{ check.label }}</span>
              <span v-if="check.decisive" class="text-[0.625rem] leading-4 font-medium tracking-[0.04em] text-fg-3 uppercase">decisive</span>
            </span>
            <span class="mt-0.5 block text-xs leading-4 text-fg-3 text-pretty">{{ check.detail }}</span>
          </span>
        </li>
      </ul>
    </section>

    <section>
      <SessionSectionLabel>What this permits</SessionSectionLabel>
      <ul v-if="policy.permissions.length" class="mt-1 space-y-1.5">
        <li v-for="permission in policy.permissions" :key="permission.label" class="flex items-start gap-2">
          <component :is="permissionIcon(permission)" :size="12" :stroke-width="2" class="mt-1 shrink-0" :class="permissionTone(permission)" aria-hidden="true" />
          <span class="text-[0.8125rem] leading-5 text-fg-2 text-pretty">{{ permission.label }}</span>
        </li>
      </ul>
      <p v-else class="mt-1 text-sm leading-5 text-fg-2 text-pretty">{{ policy.permits }}</p>
    </section>

    <section v-if="policy.restrictions.length">
      <SessionSectionLabel>Restrictions · {{ policy.restrictions.length }}</SessionSectionLabel>
      <ul class="mt-1 space-y-1.5">
        <li v-for="restriction in policy.restrictions" :key="restriction" class="flex items-start gap-2">
          <Lock :size="12" :stroke-width="1.9" class="mt-1 shrink-0 text-fg-3" aria-hidden="true" />
          <span class="text-[0.8125rem] leading-5 text-fg-2 text-pretty">{{ restriction }}</span>
        </li>
      </ul>
    </section>

    <section v-if="budgetNumbers.percent !== null">
      <div class="flex items-baseline justify-between gap-2">
        <SessionSectionLabel>Daily refund-review budget</SessionSectionLabel>
        <span class="font-mono text-[0.6875rem] leading-4 text-fg-2 tabular-nums">{{ policy.budget }}</span>
      </div>
      <p class="mt-1 font-mono text-xs leading-4 text-fg-1 tabular-nums">
        {{ policy.budgetDetail }}
      </p>
      <span
        class="mt-1.5 flex h-1.5 w-full overflow-hidden rounded-full bg-raised"
        role="img"
        :aria-label="`${budgetNumbers.percent}% of the daily budget committed`"
      >
        <span class="h-full rounded-full bg-fg-3" :style="{ width: `${budgetNumbers.percent}%` }" />
      </span>
      <SessionCaveat
        class="mt-2"
        summary="No warning threshold is defined for this budget."
        detail="The percentage is reported without alert styling because the record attaches no warning threshold."
      />
    </section>

    <SessionRawRecord :value="policy" />
  </div>
</template>

<style scoped>
.ix-rule {
  border: 1px solid var(--ix-line);
  border-radius: 10px;
  background: var(--ix-surface);
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
</style>
