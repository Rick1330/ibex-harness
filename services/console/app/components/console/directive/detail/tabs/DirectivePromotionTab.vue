<script setup lang="ts">
import { computed } from "vue"
import { ArrowLeftRight, CircleCheck, Lock, RotateCcw, ShieldAlert, Upload } from "@lucide/vue"
import GovernApprovalBlock from "@/components/console/govern/primitives/GovernApprovalBlock.vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernCheckList from "@/components/console/govern/primitives/GovernCheckList.vue"
import GovernDiffSummaryBar from "@/components/console/govern/primitives/GovernDiffSummaryBar.vue"
import GovernEmptyValue from "@/components/console/govern/primitives/GovernEmptyValue.vue"
import GovernHashTag from "@/components/console/govern/primitives/GovernHashTag.vue"
import GovernLifecyclePill from "@/components/console/govern/primitives/GovernLifecyclePill.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import GovernVersionTag from "@/components/console/govern/primitives/GovernVersionTag.vue"
import DirectivePromotionSteps from "@/components/console/directive/detail/DirectivePromotionSteps.vue"
import {
  DIRECTIVE_EVENT_LABELS,
  directiveApprovalState,
  directiveAuditEvents,
  directiveCandidate,
  directiveCheckSummary,
  directiveDiff,
  directiveLive,
  directiveRollbackTarget,
  type Directive,
} from "@/lib/directive-preview"
import { formatGovernDate, formatGovernRelative } from "@/lib/govern-format"

const props = defineProps<{ directive: Directive }>()
const emit = defineEmits<{ compare: [from: string, to: string]; audit: [] }>()

const live = computed(() => directiveLive(props.directive))
const candidate = computed(() => directiveCandidate(props.directive))
const rollbackTarget = computed(() => directiveRollbackTarget(props.directive))
const focus = computed(() => candidate.value ?? props.directive.versions[0] ?? null)
const checks = computed(() => directiveCheckSummary(focus.value))
const approval = computed(() => directiveApprovalState(candidate.value))
const latestEvent = computed(() => directiveAuditEvents(props.directive)[0] ?? null)

const rollbackDiff = computed(() =>
  live.value && rollbackTarget.value ? directiveDiff(props.directive, rollbackTarget.value.version, live.value.version) : null,
)

const blockers = computed(() => {
  const items: { key: string; label: string; detail: string; tone: "critical" | "warning" | "neutral" }[] = []
  if (!candidate.value) {
    items.push({
      key: "no-candidate",
      label: "No open candidate",
      detail: live.value ? `${live.value.version} stays live until a candidate passes the gate.` : "No version is live.",
      tone: "neutral",
    })
    return items
  }
  for (const check of candidate.value.checks.filter((entry) => entry.state === "failed")) {
    items.push({ key: check.id, label: check.name, detail: check.result ?? "Failed", tone: "critical" })
  }
  if (approval.value.state === "waiting") {
    items.push({
      key: "approval",
      label: `${approval.value.waiting} approval${approval.value.waiting === 1 ? "" : "s"} missing`,
      detail: `${approval.value.eligible.join(", ") || "No eligible approver"} · waiting ${approval.value.waitingLabel}`,
      tone: "warning",
    })
  }
  if (!items.length) {
    items.push({ key: "ready", label: "Ready to promote", detail: "Every check passed and every approval is recorded.", tone: "neutral" })
  }
  return items
})

const gate = computed(() => {
  if (!candidate.value) return []
  return [
    {
      key: "checks",
      label: "No failed checks",
      pass: checks.value.failed === 0 && checks.value.total > 0,
      detail: checks.value.total ? checks.value.label : "No checks configured",
    },
    {
      key: "approvals",
      label: "Required approvals recorded",
      pass: approval.value.required === 0 || approval.value.approved >= approval.value.required,
      detail: approval.value.required ? `${approval.value.approved} of ${approval.value.required}` : "Not required",
    },
    {
      key: "author",
      label: "Approver is not the author",
      pass: approval.value.required === 0 || approval.value.approved > 0 || !approval.value.authorExcluded,
      detail: approval.value.authorExcluded ? `${candidate.value.author} is excluded` : "No conflict recorded",
    },
  ]
})
</script>

<template>
  <div class="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
    <DirectivePromotionSteps class="xl:col-span-2" :directive="directive" />
    <div class="flex min-w-0 flex-col gap-4">
      <section class="min-w-0 rounded-lg border border-line-subtle bg-surface-1" aria-labelledby="promotion-target-title">
        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-line-subtle px-4 py-2.5">
          <div>
            <h2 id="promotion-target-title" class="text-xs font-semibold text-fg-1">Promotion target</h2>
            <p class="mt-0.5 text-[0.6875rem] leading-4 text-fg-3">{{ candidate ? "The open candidate is what a promotion would make live." : "No candidate is open right now." }}</p>
          </div>
          <GovernLifecyclePill v-if="focus" :state="focus.state" />
        </div>
        <div v-if="focus" class="px-4 py-3">
          <div class="flex flex-wrap items-center gap-2">
            <GovernVersionTag label="Version" :value="focus.version" tone="default" />
            <span class="text-xs text-fg-3">by {{ focus.author }}</span>
            <span aria-hidden="true" class="text-fg-3">·</span>
            <span class="text-xs text-fg-3" :title="focus.createdAt">opened {{ formatGovernRelative(focus.createdAt) }}</span>
          </div>
          <p v-if="focus.summary" class="mt-2 text-xs leading-5 text-fg-2">{{ focus.summary }}</p>
          <p v-else class="mt-2 text-xs text-fg-3"><GovernEmptyValue reason="No change note" /></p>
          <GovernHashTag class="mt-2.5" :hash="focus.hash" label="candidate digest" />
        </div>
      </section>

      <section class="min-w-0" aria-labelledby="promotion-checks-title">
        <div class="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="promotion-checks-title" class="text-xs font-semibold text-fg-1">Promotion checks</h2>
          <span v-if="focus && checks.total" class="font-mono text-[0.6875rem] text-fg-3 tabular-nums">{{ checks.label }}</span>
        </div>
        <GovernCheckList :items="focus?.checks ?? []" empty-label="No promotion checks are configured for this version." />
      </section>

      <GovernApprovalBlock v-if="candidate" :approval="approval" :approvals="candidate.approvals" :author="candidate.author" />
      <GovernCaveat v-else tone="info" title="Approval applies to an open candidate">
        There is no candidate waiting for approval. {{ latestEvent ? `${DIRECTIVE_EVENT_LABELS[latestEvent.action]} is the latest recorded event.` : "" }}
      </GovernCaveat>

      <section class="min-w-0 rounded-lg border border-line-subtle bg-surface-1" aria-labelledby="promotion-rollback-title">
        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-line-subtle px-4 py-2.5">
          <div>
            <h2 id="promotion-rollback-title" class="text-xs font-semibold text-fg-1">Rollback plan</h2>
            <p class="mt-0.5 text-[0.6875rem] leading-4 text-fg-3">Rollback promotes the previous live version again.</p>
          </div>
          <GovernVersionTag v-if="rollbackTarget" label="Target" :value="rollbackTarget.version" tone="default" />
        </div>
        <div v-if="rollbackTarget && live" class="px-4 py-3">
          <p class="text-xs leading-5 text-fg-2">
            Rolling back replaces <span class="font-mono text-fg-1">{{ live.version }}</span> with
            <span class="font-mono text-fg-1">{{ rollbackTarget.version }}</span> (live {{ formatGovernDate(rollbackTarget.liveFrom) }} – {{ formatGovernDate(rollbackTarget.liveTo) }}).
          </p>
          <div v-if="rollbackDiff" class="mt-2">
            <GovernDiffSummaryBar :summary="rollbackDiff.summary" :from="rollbackTarget.version" :to="live.version" />
          </div>
          <div class="mt-3 flex flex-wrap items-center gap-2">
            <button type="button" class="ix-button-secondary h-8 text-xs" @click="emit('compare', rollbackTarget.version, live.version)">
              <ArrowLeftRight :size="12" :stroke-width="1.9" aria-hidden="true" />
              Compare {{ rollbackTarget.version }} → {{ live.version }}
            </button>
            <GovernLockedAction label="Roll back" :icon="RotateCcw" variant="secondary" size="sm" />
          </div>
        </div>
        <div v-else class="px-4 py-3">
          <GovernCaveat tone="info" title="No rollback target">
            {{ live ? `${live.version} is the first live version, so there is nothing earlier to restore.` : "No version has served traffic yet." }}
          </GovernCaveat>
        </div>
      </section>
    </div>

    <div class="flex min-w-0 flex-col gap-4">
      <section class="min-w-0 rounded-lg border border-line-subtle bg-surface-1 p-4" aria-labelledby="promotion-blockers-title">
        <h2 id="promotion-blockers-title" class="text-xs font-semibold text-fg-1">Promotion readiness</h2>
        <ul class="mt-2 space-y-2">
          <li v-for="item in blockers" :key="item.key" class="flex items-start gap-2">
            <span
              class="mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded-full border"
              :class="item.tone === 'critical' ? 'border-transparent bg-transparent text-crit' : item.tone === 'warning' ? 'border-transparent bg-transparent text-warn' : 'border-transparent bg-transparent text-ok'"
            >
              <ShieldAlert v-if="item.tone !== 'neutral'" :size="11" :stroke-width="2" aria-hidden="true" />
              <CircleCheck v-else :size="11" :stroke-width="2" aria-hidden="true" />
            </span>
            <span class="min-w-0">
              <span class="block text-xs font-medium text-fg-1">{{ item.label }}</span>
              <span class="block text-[0.6875rem] leading-4 text-fg-3">{{ item.detail }}</span>
            </span>
          </li>
        </ul>

        <dl v-if="gate.length" class="mt-3 space-y-1.5 border-t border-line-subtle pt-2.5 text-xs leading-4">
          <div v-for="entry in gate" :key="entry.key" class="flex items-baseline justify-between gap-3">
            <dt class="flex items-center gap-1.5 text-fg-3">
              <CircleCheck :size="11" :stroke-width="2" :class="entry.pass ? 'text-ok' : 'text-crit'" aria-hidden="true" />
              {{ entry.label }}
            </dt>
            <dd class="truncate text-fg-2">{{ entry.detail }}</dd>
          </div>
        </dl>

        <div class="mt-3 flex flex-wrap items-center gap-2 border-t border-line-subtle pt-3">
          <GovernLockedAction :label="candidate ? `Promote ${candidate.version}` : 'Promote candidate'" :icon="Upload" variant="primary" size="sm" />
          <span class="inline-flex items-center gap-1 text-[0.6875rem] text-fg-3">
            <Lock :size="10" :stroke-width="1.9" aria-hidden="true" />
            Requires a privileged write contract
          </span>
        </div>
      </section>

      <section class="min-w-0 rounded-lg border border-line-subtle bg-surface-1 p-4" aria-labelledby="promotion-live-title">
        <h2 id="promotion-live-title" class="text-xs font-semibold text-fg-1">Currently live</h2>
        <div v-if="live" class="mt-2">
          <div class="flex flex-wrap items-center gap-2">
            <GovernVersionTag label="Version" :value="live.version" tone="default" />
            <span class="text-xs text-fg-3">since {{ formatGovernDate(live.liveFrom) }}</span>
          </div>
          <GovernHashTag class="mt-2" :hash="live.hash" label="live digest" />
          <button type="button" class="mt-3 text-xs text-fg-3 underline decoration-line-strong underline-offset-3 hover:text-fg-1" @click="emit('audit')">
            Open the audit trail
          </button>
        </div>
        <p v-else class="mt-2 text-xs text-fg-3">No live version.</p>
      </section>
    </div>
  </div>
</template>
