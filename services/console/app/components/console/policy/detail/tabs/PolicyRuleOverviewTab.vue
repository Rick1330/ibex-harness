<script setup lang="ts">
import { computed } from "vue"
import { ArrowDown, ArrowRight, ArrowUp, History, Minus, TriangleAlert } from "@lucide/vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernConditionCode from "@/components/console/govern/primitives/GovernConditionCode.vue"
import GovernEffectTag from "@/components/console/govern/primitives/GovernEffectTag.vue"
import GovernEmptyValue from "@/components/console/govern/primitives/GovernEmptyValue.vue"
import GovernModeTag from "@/components/console/govern/primitives/GovernModeTag.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import { formatGovernNumber, formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"
import {
  POLICY_EFFECT_DESCRIPTIONS,
  POLICY_MODE_DESCRIPTIONS,
  policyFiredDelta,
  policyRuleApprovalStats,
  policyRuleLastFired,
  policyRuleProvenance,
  policyRuleSentence,
  policyRuleRuns,
  policySnapshotState,
  type PolicyRule,
  type PolicyRuleRevision,
  type PolicyRuleTab,
  type PolicySnapshot,
} from "@/lib/policy-preview"
import { policySnapshotHref } from "@/lib/govern-query"

const props = defineProps<{
  rule: PolicyRule
  revision: PolicyRuleRevision
  snapshot: PolicySnapshot
}>()

const emit = defineEmits<{ tab: [tab: PolicyRuleTab]; revision: [revision: number] }>()

const sentence = computed(() => policyRuleSentence(props.revision) ?? props.revision.summary)
const delta = computed(() => policyFiredDelta(props.rule))
const provenance = computed(() => policyRuleProvenance(props.rule.id))
const lastFired = computed(() => policyRuleLastFired(props.rule.id))
const approval = computed(() => (props.revision.effect === "require_approval" ? policyRuleApprovalStats(props.rule.id) : null))
const runs = computed(() => policyRuleRuns(props.rule.id))
const snapshotState = computed(() => policySnapshotState(props.snapshot.id))

const deltaTone = computed(() => (delta.value.direction === "up" ? "text-warn" : delta.value.direction === "down" ? "text-ok" : "text-fg-1"))
const deltaIcon = computed(() => (delta.value.direction === "up" ? ArrowUp : delta.value.direction === "down" ? ArrowDown : Minus))
</script>

<template>
  <div class="grid min-w-0 gap-3 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
    <div class="flex min-w-0 flex-col gap-3">
      <section class="rounded-lg border border-line-subtle bg-surface-1" aria-labelledby="rule-what">
        <header class="flex flex-wrap items-center justify-between gap-2 border-b border-line-subtle px-4 py-2.5">
          <h2 id="rule-what" class="text-sm font-semibold text-fg-1">What this rule does</h2>
          <div class="flex items-center gap-1.5">
            <GovernEffectTag :effect="revision.effect" />
            <GovernModeTag :mode="revision.mode" />
          </div>
        </header>
        <div class="px-4 py-3">
          <p class="text-sm leading-6 text-fg-1">{{ sentence }}</p>
          <dl class="mt-3 grid gap-3 sm:grid-cols-2">
            <div class="min-w-0">
              <dt class="text-[0.6875rem] font-medium tracking-[0.06em] text-fg-3 uppercase">Effect</dt>
              <dd class="mt-1 text-xs leading-5 text-fg-2">{{ POLICY_EFFECT_DESCRIPTIONS[revision.effect] }}</dd>
            </div>
            <div class="min-w-0">
              <dt class="text-[0.6875rem] font-medium tracking-[0.06em] text-fg-3 uppercase">Mode</dt>
              <dd class="mt-1 text-xs leading-5 text-fg-2">{{ POLICY_MODE_DESCRIPTIONS[revision.mode] }}</dd>
            </div>
          </dl>
          <div class="mt-3 border-t border-line-subtle pt-3">
            <p class="text-[0.6875rem] font-medium tracking-[0.06em] text-fg-3 uppercase">Expression</p>
            <div class="mt-1"><GovernConditionCode :code="revision.condition" /></div>
          </div>
        </div>
      </section>

      <div class="grid grid-cols-2 gap-2 sm:gap-3 xl:grid-cols-4">
        <GovernStatTile label="Fired (7 days)" :value="rule.fired === null ? 'Not reported' : formatGovernNumber(rule.fired)" :helper="rule.fired === null ? 'No decision data joined' : `${delta.label} vs previous 7 days`" compact>
          <span v-if="rule.fired !== null" class="inline-flex items-center gap-1 font-mono text-[0.625rem]" :class="deltaTone">
            <component :is="deltaIcon" :size="9" :stroke-width="2.4" aria-hidden="true" />
            {{ delta.label }}
          </span>
        </GovernStatTile>
        <GovernStatTile label="Linked runs" :value="formatGovernNumber(provenance.linked)" :helper="`${provenance.complete} complete · ${provenance.partial} partial`" :tone="provenance.partial > 0 ? 'warning' : 'default'" compact />
        <GovernStatTile label="Last fired" :value="lastFired ? formatGovernRelative(lastFired.at) : '—'" :helper="lastFired ? formatGovernStamp(lastFired.at) : 'No linked decision'" compact />
        <GovernStatTile label="Revision" :value="`@${revision.revision}`" :helper="`of ${rule.revisions.length} revisions`" compact />
      </div>

      <section v-if="approval" class="rounded-lg border border-line-subtle bg-surface-1" aria-labelledby="rule-approvals">
        <header class="flex items-center justify-between gap-2 border-b border-line-subtle px-4 py-2.5">
          <h2 id="rule-approvals" class="text-sm font-semibold text-fg-1">Approvals</h2>
          <button type="button" class="text-xs font-medium text-fg-2 underline decoration-line-strong underline-offset-3 hover:text-fg-1" @click="emit('tab', 'fires')">
            See linked runs
          </button>
        </header>
        <dl class="grid grid-cols-2 gap-px bg-line-subtle sm:grid-cols-4">
          <div class="bg-surface-1 px-4 py-2.5">
            <dt class="text-[0.6875rem] text-fg-3">Granted</dt>
            <dd class="mt-0.5 font-mono text-lg leading-6 font-semibold text-ok tabular-nums">{{ approval.granted }}</dd>
          </div>
          <div class="bg-surface-1 px-4 py-2.5">
            <dt class="text-[0.6875rem] text-fg-3">Denied</dt>
            <dd class="mt-0.5 font-mono text-lg leading-6 font-semibold text-crit tabular-nums">{{ approval.denied }}</dd>
          </div>
          <div class="bg-surface-1 px-4 py-2.5">
            <dt class="text-[0.6875rem] text-fg-3">Pending</dt>
            <dd class="mt-0.5 font-mono text-lg leading-6 font-semibold text-warn tabular-nums">{{ approval.pending }}</dd>
          </div>
          <div class="bg-surface-1 px-4 py-2.5">
            <dt class="text-[0.6875rem] text-fg-3">Median wait</dt>
            <dd class="mt-0.5 font-mono text-lg leading-6 font-semibold text-fg-1 tabular-nums">
              {{ approval.medianMinutes === null ? "—" : `${approval.medianMinutes} min` }}
            </dd>
          </div>
        </dl>
      </section>

      <GovernCaveat v-if="provenance.partial > 0" tone="warning" title="Partial provenance.">
        {{ provenance.partial }} of {{ provenance.linked }} linked runs do not join to a certified evidence record, so fire counts may be low. This is a gap in the join, not proof the rule was skipped.
      </GovernCaveat>
    </div>

    <div class="flex min-w-0 flex-col gap-3">
      <section class="rounded-lg border border-line-subtle bg-surface-1" aria-labelledby="rule-facts">
        <header class="border-b border-line-subtle px-4 py-2.5">
          <h2 id="rule-facts" class="text-sm font-semibold text-fg-1">Facts</h2>
        </header>
        <dl class="divide-y divide-line-subtle">
          <div class="flex items-baseline justify-between gap-3 px-4 py-2">
            <dt class="text-xs text-fg-3">Owner</dt>
            <dd class="text-xs text-fg-1">{{ rule.owner }}</dd>
          </div>
          <div class="flex items-baseline justify-between gap-3 px-4 py-2">
            <dt class="text-xs text-fg-3">Area</dt>
            <dd class="text-xs text-fg-1">{{ rule.area }}</dd>
          </div>
          <div class="flex items-baseline justify-between gap-3 px-4 py-2">
            <dt class="text-xs text-fg-3">Scope</dt>
            <dd class="font-mono text-[0.6875rem] text-fg-2">{{ rule.scope }}</dd>
          </div>
          <div class="flex items-baseline justify-between gap-3 px-4 py-2">
            <dt class="text-xs text-fg-3">Changed</dt>
            <dd class="text-right">
              <span class="block text-xs text-fg-1" :title="formatGovernStamp(revision.effectiveFrom)">{{ formatGovernRelative(revision.effectiveFrom) }}</span>
              <span class="block text-[0.625rem] text-fg-3">by {{ revision.changedBy }}</span>
            </dd>
          </div>
          <div class="flex items-baseline justify-between gap-3 px-4 py-2">
            <dt class="text-xs text-fg-3">Change note</dt>
            <dd class="max-w-[22rem] text-right text-xs leading-4 text-fg-2">{{ revision.changeSummary }}</dd>
          </div>
        </dl>
      </section>

      <section class="rounded-lg border border-line-subtle bg-surface-1" aria-labelledby="rule-snapshot">
        <header class="flex items-center justify-between gap-2 border-b border-line-subtle px-4 py-2.5">
          <h2 id="rule-snapshot" class="text-sm font-semibold text-fg-1">Snapshot</h2>
          <span
            class="inline-flex h-5 items-center rounded-full border px-1.5 text-[0.625rem] font-medium"
            :class="snapshotState === 'live' ? 'border-transparent bg-transparent text-ok' : 'border-line bg-raised text-fg-3'"
          >
            {{ snapshotState === "live" ? "Live" : "Superseded" }}
          </span>
        </header>
        <div class="px-4 py-3">
          <NuxtLink :to="policySnapshotHref(snapshot.id)" class="font-mono text-xs text-fg-1 underline decoration-line-strong underline-offset-3 hover:text-accent">
            {{ snapshot.id }}
          </NuxtLink>
          <p class="mt-1 text-xs leading-4 text-fg-3">Effective {{ formatGovernStamp(snapshot.effectiveFrom) }} · published by {{ snapshot.publishedBy }}</p>
          <p class="mt-2 text-xs leading-4 text-fg-2">{{ snapshot.message }}</p>
        </div>
      </section>

      <section class="rounded-lg border border-line-subtle bg-surface-1" aria-labelledby="rule-revisions">
        <header class="flex items-center justify-between gap-2 border-b border-line-subtle px-4 py-2.5">
          <h2 id="rule-revisions" class="text-sm font-semibold text-fg-1">Revisions</h2>
          <button type="button" class="inline-flex items-center gap-1 text-xs text-fg-3 hover:text-fg-1" @click="emit('tab', 'history')">
            <History :size="12" :stroke-width="1.9" aria-hidden="true" />
            Compare
          </button>
        </header>
        <ul class="divide-y divide-line-subtle">
          <li v-for="entry in rule.revisions" :key="entry.revision" class="flex items-center gap-2 px-4 py-2">
            <button
              type="button"
              class="min-w-0 flex-1 text-left"
              :aria-current="entry.revision === props.revision.revision ? 'true' : undefined"
              @click="emit('revision', entry.revision)"
            >
              <span class="flex items-center gap-1.5">
                <span class="font-mono text-xs text-fg-1">@{{ entry.revision }}</span>
                <span class="text-[0.625rem] text-fg-3">{{ POLICY_EFFECT_DESCRIPTIONS[entry.effect].split(".")[0] }}</span>
              </span>
              <span class="mt-0.5 block truncate text-[0.625rem] text-fg-3">{{ formatGovernRelative(entry.effectiveFrom) }} · {{ entry.changedBy }}</span>
            </button>
            <span v-if="entry.revision === props.revision.revision" class="size-1.5 rounded-full bg-accent-memory" role="img" aria-label="Shown" />
            <ArrowRight v-else :size="11" :stroke-width="1.8" class="text-fg-off" aria-hidden="true" />
          </li>
          <li v-if="rule.revisions.length === 0" class="px-4 py-3">
            <GovernEmptyValue reason="No revisions recorded for this rule" />
          </li>
        </ul>
        <p class="border-t border-line-subtle px-4 py-2 text-[0.625rem] leading-3.5 text-fg-3">
          {{ runs.length }} linked run{{ runs.length === 1 ? "" : "s" }} in the sample.
        </p>
      </section>

      <span v-if="provenance.partial > 0" class="sr-only">
        <TriangleAlert aria-hidden="true" /> Partial provenance affects the fire counts.
      </span>
    </div>
  </div>
</template>
