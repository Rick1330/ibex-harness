<script setup lang="ts">
import { computed, ref } from "vue"
import { ArrowLeft, ArrowRight, ChevronLeft, ChevronRight, Download, Radio } from "@lucide/vue"
import GovernAboutPopover from "@/components/console/govern/primitives/GovernAboutPopover.vue"
import GovernActorBadge from "@/components/console/govern/primitives/GovernActorBadge.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernDataSourceChip from "@/components/console/govern/primitives/GovernDataSourceChip.vue"
import GovernDiffView from "@/components/console/govern/primitives/GovernDiffView.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernEvidenceChip from "@/components/console/govern/primitives/GovernEvidenceChip.vue"
import GovernIdChip from "@/components/console/govern/primitives/GovernIdChip.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import GovernResultChip from "@/components/console/govern/primitives/GovernResultChip.vue"
import GovernTabBar from "@/components/console/govern/primitives/GovernTabBar.vue"
import { useGovernShortcuts } from "@/composables/useGovernShortcuts"
import { formatGovernNumber, formatGovernStamp, formatGovernStampMillis } from "@/lib/govern-format"
import {
  AUDIT_EVENT_TAB_LABELS,
  auditEventHref,
  type AuditEventDetailState,
  type AuditEventTab,
} from "@/lib/govern-query"
import {
  AUDIT_EVIDENCE_LABELS,
  AUDIT_ORIGIN_LABELS,
  AUDIT_TARGET_TYPE_LABELS,
  auditAction,
  auditActorAuth,
  auditActorSubline,
  auditDiffChangedCount,
  auditEventJson,
  auditIdempotencyAnswer,
  auditPolicyHref,
  auditPrevNext,
  auditRelated,
  auditTargetHref,
  type AuditEvent,
} from "@/lib/audit-preview"

const props = defineProps<{ event: AuditEvent; state: AuditEventDetailState }>()
const emit = defineEmits<{ update: [state: AuditEventDetailState] }>()

const about = ref<InstanceType<typeof GovernAboutPopover> | null>(null)
const copied = ref(false)
let copyTimer: ReturnType<typeof setTimeout> | null = null

const tabs = (Object.keys(AUDIT_EVENT_TAB_LABELS) as AuditEventTab[]).map((tab) => ({
  id: tab,
  label: AUDIT_EVENT_TAB_LABELS[tab],
}))
const related = computed(() => auditRelated(props.event))
const badges = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  if (related.value.length) map.related = String(related.value.length)
  return map
})
const neighbours = computed(() => auditPrevNext(props.event.id))
const action = computed(() => auditAction(props.event.action))
const idempotency = computed(() => auditIdempotencyAnswer(props.event))
const changedKeys = computed(() => (props.event.diff ? auditDiffChangedCount(props.event.diff) : 0))
const targetHref = computed(() => auditTargetHref(props.event.target))
const raw = computed(() => JSON.stringify(auditEventJson(props.event), null, 2))

function selectTab(tab: string): void {
  emit("update", { tab: tab as AuditEventTab })
}

function go(event: AuditEvent | null): void {
  if (!event) return
  void navigateTo(auditEventHref(event.id))
}

function copyLink(): void {
  if (!import.meta.client) return
  void navigator.clipboard.writeText(window.location.href)
}

async function copyRaw(): Promise<void> {
  if (!import.meta.client) return
  try {
    await navigator.clipboard.writeText(raw.value)
  } catch {
    return
  }
  copied.value = true
  if (copyTimer) clearTimeout(copyTimer)
  copyTimer = setTimeout(() => {
    copied.value = false
  }, 1_600)
}

useGovernShortcuts({
  keys: {
    "[": () => go(neighbours.value.previous),
    "]": () => go(neighbours.value.next),
    y: copyLink,
  },
})
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">
    <header class="flex flex-col gap-3">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <NuxtLink
            to="/audit"
            class="inline-flex items-center gap-1 text-xs text-fg-3 transition-colors hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
          >
            <ArrowLeft :size="12" :stroke-width="1.9" aria-hidden="true" />
            Audit log
          </NuxtLink>
          <div class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
            <span class="font-mono text-[0.6875rem] leading-4 text-fg-3">{{ event.action }}</span>
            <GovernIdChip :value="event.id" label="Event ID" />
          </div>
          <h1 class="mt-1 max-w-3xl ix-page-title text-fg-1">{{ event.summary }}</h1>
          <p class="mt-1 text-sm leading-5 text-fg-2">{{ action.sentence }}.</p>
          <div class="mt-2 flex flex-wrap items-center gap-1.5">
            <GovernResultChip :result="event.result" />
            <GovernEvidenceChip :evidence="event.evidence" />
            <span class="ix-preview-chip">{{ AUDIT_ORIGIN_LABELS[event.origin] }}</span>
            <span v-if="event.stepUp" class="ix-preview-chip border-accent/40 text-accent">Step-up verified</span>
          </div>
        </div>

        <div class="flex shrink-0 flex-wrap items-center gap-2">
          <GovernDataSourceChip @open="about?.open()" />
      <GovernAboutPopover
        ref="about"
        verdict="This event is one recorded preview fixture. The append-only audit stream is not connected, so no completeness or integrity claim is made."
        contract="operator.audit.list.v1"
        scope="org_demo_42 · workspace ws_42"
        range="Recorded preview event"
        coverage="Preview fixture · no audit stream connected"
        phase="A3 · Phase B2"
        claim="No enforcement, billing, or deletion claim."
        :notes="[
          { lead: 'The record is the source of truth.', body: 'This page renders the event fields as recorded. Missing fields stay missing rather than being reconstructed from neighbouring events.' },
          { lead: 'Idempotency answers “exactly once”.', body: 'The effects and duplicate counts come from the record, not from retry logic inferred in the console.' },
        ]"
      />
          <div class="inline-flex items-center gap-1">
            <button
              type="button"
              class="inline-flex size-8 items-center justify-center rounded-md border border-line-subtle bg-surface-1 text-fg-3 transition-colors hover:border-line hover:text-fg-1 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
              :disabled="!neighbours.previous"
              :aria-label="neighbours.previous ? `Newer event: ${neighbours.previous.action}` : 'Already at the newest event'"
              :title="neighbours.previous ? 'Newer event · [' : 'Already at the newest event'"
              @click="go(neighbours.previous)"
            >
              <ChevronLeft :size="14" :stroke-width="1.9" aria-hidden="true" />
            </button>
            <span class="font-mono text-[0.625rem] text-fg-3">{{ neighbours.index + 1 }} / {{ neighbours.total }}</span>
            <button
              type="button"
              class="inline-flex size-8 items-center justify-center rounded-md border border-line-subtle bg-surface-1 text-fg-3 transition-colors hover:border-line hover:text-fg-1 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
              :disabled="!neighbours.next"
              :aria-label="neighbours.next ? `Older event: ${neighbours.next.action}` : 'Already at the oldest event'"
              :title="neighbours.next ? 'Older event · ]' : 'Already at the oldest event'"
              @click="go(neighbours.next)"
            >
              <ChevronRight :size="14" :stroke-width="1.9" aria-hidden="true" />
            </button>
          </div>
          <GovernLockedAction label="Export event" :icon="Download" />
        </div>
      </div>

    </header>

    <section
      class="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg border px-3.5 py-3"
      :class="event.result === 'applied' && idempotency.ok ? 'border-ok/30 bg-ok-tint/50' : 'border-warn/30 bg-warn-tint/40'"
      aria-label="Idempotency"
    >
      <div class="min-w-0">
        <p class="flex items-center gap-1.5 text-[0.6875rem] font-medium tracking-wide text-fg-3 uppercase">
          <Radio :size="12" :stroke-width="1.9" aria-hidden="true" />
          Idempotency
        </p>
        <p class="mt-0.5 text-base leading-6 font-semibold" :class="event.result === 'applied' && idempotency.ok ? 'text-ok' : 'text-warn'">
          {{ idempotency.label }}
        </p>
      </div>
      <p class="max-w-xl text-xs leading-5 text-fg-2">{{ idempotency.detail }}</p>
      <div class="ml-auto flex flex-wrap items-center gap-2 text-[0.6875rem] text-fg-3">
        <span class="inline-flex items-center gap-1 rounded-full border border-line-subtle bg-surface-1 px-2 py-1 font-mono">
          {{ event.idempotency.effects }} effect{{ event.idempotency.effects === 1 ? "" : "s" }}
        </span>
        <span class="inline-flex items-center gap-1 rounded-full border border-line-subtle bg-surface-1 px-2 py-1 font-mono">
          {{ event.idempotency.duplicates }} duplicate{{ event.idempotency.duplicates === 1 ? "" : "s" }}
        </span>
        <GovernCopyId :id="event.idempotency.key" label="Idempotency key" />
      </div>
    </section>

    <dl class="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line-subtle bg-line-subtle sm:grid-cols-2 xl:grid-cols-4">
      <div class="bg-surface-1 px-3 py-2.5">
        <dt class="text-[0.6875rem] text-fg-3">Occurred</dt>
        <dd class="mt-0.5 font-mono text-xs text-fg-1" :title="formatGovernStampMillis(event.at)">
          {{ formatGovernStamp(event.at) }}
        </dd>
      </div>
      <div class="bg-surface-1 px-3 py-2.5">
        <dt class="text-[0.6875rem] text-fg-3">Actor</dt>
        <dd class="mt-1">
          <GovernActorBadge
            :name="event.actor.name"
            :type="event.actor.type"
            :step-up="event.stepUp"
            :subline="auditActorSubline(event)"
            size="sm"
          />
        </dd>
      </div>
      <div class="bg-surface-1 px-3 py-2.5">
        <dt class="text-[0.6875rem] text-fg-3">Authentication</dt>
        <dd class="mt-0.5 text-xs text-fg-2">{{ auditActorAuth(event) }}</dd>
      </div>
      <div class="bg-surface-1 px-3 py-2.5">
        <dt class="text-[0.6875rem] text-fg-3">Origin</dt>
        <dd class="mt-0.5 text-xs text-fg-1">{{ AUDIT_ORIGIN_LABELS[event.origin] }}</dd>
      </div>
      <div class="bg-surface-1 px-3 py-2.5">
        <dt class="text-[0.6875rem] text-fg-3">Target</dt>
        <dd class="mt-0.5 min-w-0">
          <NuxtLink
            v-if="targetHref"
            :to="targetHref"
            class="block truncate text-xs text-fg-1 underline decoration-line-strong underline-offset-2 hover:text-accent-memory"
            :title="event.target.name"
          >
            {{ event.target.name }}
          </NuxtLink>
          <span v-else class="block truncate text-xs text-fg-1">{{ event.target.name }}</span>
          <span class="mt-0.5 block truncate font-mono text-[0.625rem] text-fg-3">
            {{ AUDIT_TARGET_TYPE_LABELS[event.target.type] }} · {{ event.target.id }}
          </span>
        </dd>
      </div>
      <div class="bg-surface-1 px-3 py-2.5">
        <dt class="text-[0.6875rem] text-fg-3">Request</dt>
        <dd class="mt-0.5 flex items-center gap-1.5">
          <span class="font-mono text-xs text-fg-1">{{ event.request.method }} {{ event.request.status }}</span>
          <span class="font-mono text-[0.625rem] text-fg-3">{{ formatGovernNumber(event.request.durationMs) }}ms</span>
        </dd>
        <dd class="mt-0.5 truncate font-mono text-[0.625rem] text-fg-3" :title="event.request.route">{{ event.request.route }}</dd>
      </div>
      <div class="bg-surface-1 px-3 py-2.5">
        <dt class="text-[0.6875rem] text-fg-3">Evidence</dt>
        <dd class="mt-1 flex flex-wrap items-center gap-1.5">
          <GovernEvidenceChip :evidence="event.evidence" />
        </dd>
        <dd class="mt-1 text-[0.625rem] text-fg-3">{{ AUDIT_EVIDENCE_LABELS[event.evidence] }} evidence</dd>
      </div>
      <div class="bg-surface-1 px-3 py-2.5">
        <dt class="text-[0.6875rem] text-fg-3">Request ID</dt>
        <dd class="mt-0.5"><GovernIdChip :value="event.requestId" label="Request ID" /></dd>
      </div>
    </dl>

    <GovernTabBar
      :tabs="tabs"
      :model-value="state.tab"
      :badges="badges"
      aria-label="Event sections"
      @update:model-value="selectTab"
    />

    <section v-if="state.tab === 'changes'" class="flex flex-col gap-2">
      <template v-if="event.diff">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <h2 class="text-sm font-semibold text-fg-1">
            {{ changedKeys }} changed key{{ changedKeys === 1 ? "" : "s" }}
          </h2>
          <span class="text-[0.6875rem] text-fg-3">Unchanged keys are hidden by default.</span>
        </div>
        <div class="rounded-lg border border-line-subtle bg-surface-1 p-3">
          <GovernDiffView
            :before="event.diff.before"
            :after="event.diff.after"
            :summaries="event.diff.summaries"
            :redactions="event.request.redactions"
            default-mode="changed"
          />
        </div>
      </template>
      <GovernEmptyState
        v-else
        title="No field changes recorded"
        reason="This event records a request and its outcome, not a before/after state change. Missing fields are never reconstructed here."
        next-step="Open Request for the recorded call, or Related for events that share its target or idempotency key."
      />
    </section>

    <section v-else-if="state.tab === 'request'" class="flex flex-col gap-3">
      <div class="grid gap-px overflow-hidden rounded-lg border border-line-subtle bg-line-subtle sm:grid-cols-2 xl:grid-cols-4">
        <div class="bg-surface-1 px-3 py-2.5">
          <p class="text-[0.6875rem] text-fg-3">Method</p>
          <p class="mt-0.5 font-mono text-xs text-fg-1">{{ event.request.method }}</p>
        </div>
        <div class="bg-surface-1 px-3 py-2.5">
          <p class="text-[0.6875rem] text-fg-3">Route</p>
          <p class="mt-0.5 truncate font-mono text-xs text-fg-1" :title="event.request.route">{{ event.request.route }}</p>
        </div>
        <div class="bg-surface-1 px-3 py-2.5">
          <p class="text-[0.6875rem] text-fg-3">Status</p>
          <p class="mt-0.5 font-mono text-xs text-fg-1">{{ event.request.status }}</p>
        </div>
        <div class="bg-surface-1 px-3 py-2.5">
          <p class="text-[0.6875rem] text-fg-3">Duration</p>
          <p class="mt-0.5 font-mono text-xs text-fg-1">{{ formatGovernNumber(event.request.durationMs) }}ms</p>
        </div>
      </div>

      <div class="grid gap-3 sm:grid-cols-2">
        <div class="rounded-lg border border-line-subtle bg-surface-1 p-3">
          <h2 class="text-sm font-semibold text-fg-1">Request headers</h2>
          <ul v-if="event.request.headers.length" class="mt-2 space-y-1">
            <li v-for="header in event.request.headers" :key="header" class="break-all font-mono text-[0.6875rem] leading-4 text-fg-2">
              {{ header }}
            </li>
          </ul>
          <p v-else class="mt-2 text-xs text-fg-3">No headers recorded for this request.</p>
        </div>

        <div class="rounded-lg border border-line-subtle bg-surface-1 p-3">
          <h2 class="text-sm font-semibold text-fg-1">Redactions</h2>
          <ul v-if="event.request.redactions.length" class="mt-2 space-y-2">
            <li v-for="redaction in event.request.redactions" :key="redaction.field" class="rounded-lg border border-line-subtle bg-surface-2 px-2.5 py-2">
              <p class="font-mono text-[0.6875rem] text-fg-1">{{ redaction.field }}</p>
              <p class="mt-0.5 text-xs leading-4 text-fg-2">{{ redaction.reason }}</p>
              <p v-if="redaction.ruleId" class="mt-0.5 font-mono text-[0.625rem] text-fg-3">{{ redaction.ruleId }}</p>
            </li>
          </ul>
          <p v-else class="mt-2 text-xs text-fg-3">No fields were redacted in this record.</p>
        </div>
      </div>

      <div class="rounded-lg border border-line-subtle bg-surface-1 p-3">
        <h2 class="text-sm font-semibold text-fg-1">Request body</h2>
        <pre
          v-if="event.request.body"
          class="ix-scroll mt-2 overflow-auto rounded-lg border border-line-subtle bg-surface-2 p-3 font-mono text-[0.6875rem] leading-5 text-fg-2"
          style="max-height: 20rem"
        >{{ JSON.stringify(event.request.body, null, 2) }}</pre>
        <p v-else class="mt-2 text-xs text-fg-3">No request body was recorded.</p>
      </div>

      <div v-if="event.retry" class="rounded-lg border border-warn/30 bg-warn-tint/30 p-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-sm font-semibold text-fg-1">Retry history</h2>
          <span class="font-mono text-[0.6875rem] text-fg-3">
            {{ event.retry.nextAt ? `next ${formatGovernStamp(event.retry.nextAt)}` : "no retry scheduled" }}
          </span>
        </div>
        <p class="mt-1 text-xs leading-4 text-fg-2">{{ event.retry.reason }}</p>
        <ol class="mt-2 space-y-1.5">
          <li v-for="attempt in event.retry.attempts" :key="attempt.at" class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-xs">
            <span class="font-mono text-[0.6875rem] text-fg-3">{{ formatGovernStamp(attempt.at) }}</span>
            <span class="text-fg-1">{{ attempt.outcome }}</span>
          </li>
        </ol>
      </div>
    </section>

    <section v-else-if="state.tab === 'related'" class="flex flex-col gap-2">
      <div v-if="related.length" class="divide-y divide-line-subtle overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
        <NuxtLink
          v-for="entry in related"
          :key="entry.id"
          :to="auditEventHref(entry.id)"
          class="flex min-w-0 items-start gap-3 px-3.5 py-3 transition-colors hover:bg-surface-2/60 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-accent-memory"
        >
          <span class="mt-0.5 w-28 shrink-0 font-mono text-[0.6875rem] text-fg-3" :title="formatGovernStampMillis(entry.at)">
            {{ formatGovernStamp(entry.at) }}
          </span>
          <span class="min-w-0 flex-1">
            <span class="flex flex-wrap items-center gap-1.5">
              <span class="font-mono text-[0.6875rem] text-fg-1">{{ entry.action }}</span>
              <GovernResultChip :result="entry.result" />
            </span>
            <span class="mt-0.5 block truncate text-xs text-fg-3">{{ entry.summary }}</span>
            <span class="mt-0.5 block truncate text-[0.625rem] text-fg-3">
              {{ entry.actor.name }} · {{ entry.id }}
            </span>
          </span>
          <ArrowRight :size="13" :stroke-width="1.8" class="mt-1 shrink-0 text-fg-3" aria-hidden="true" />
        </NuxtLink>
      </div>
      <GovernEmptyState
        v-else
        title="No related events"
        reason="No other recorded event shares this target, request ID, or idempotency key within the recorded window."
        next-step="Browse the audit log to see events around this time."
      />
    </section>

    <section v-else class="flex flex-col gap-2">
      <div class="flex items-center justify-between gap-2">
        <h2 class="text-sm font-semibold text-fg-1">Raw event record</h2>
        <button type="button" class="ix-button-secondary h-7 px-2.5 text-[0.6875rem]" @click="copyRaw">
          {{ copied ? "Copied" : "Copy JSON" }}
        </button>
      </div>
      <pre class="ix-scroll max-h-[36rem] overflow-auto rounded-lg border border-line-subtle bg-surface-1 p-3 font-mono text-[0.6875rem] leading-5 text-fg-2">{{ raw }}</pre>
      <p class="text-[0.6875rem] leading-4 text-fg-3">
        This is the recorded fixture, not a live API response. Nulls mean the field was not recorded.
      </p>
    </section>

    <div class="flex flex-wrap items-center gap-2 border-t border-line-subtle pt-2">
      <NuxtLink
        v-if="event.policy"
        :to="auditPolicyHref(event.policy)"
        class="text-[0.6875rem] text-fg-2 underline decoration-line-strong underline-offset-2 hover:text-fg-1"
      >
        Policy decision: {{ event.policy.decision }} · {{ event.policy.ruleId }} rev {{ event.policy.ruleRevision }} ·
        snapshot {{ event.policy.snapshotId }}
      </NuxtLink>
      <span v-else class="text-[0.6875rem] text-fg-3">
        No policy decision was recorded for this action.
      </span>
    </div>
  </div>
</template>
