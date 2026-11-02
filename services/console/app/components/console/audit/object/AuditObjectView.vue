<script setup lang="ts">
import { computed, ref } from "vue"
import { ArrowLeft, Download, History } from "@lucide/vue"
import GovernAboutPopover from "@/components/console/govern/primitives/GovernAboutPopover.vue"
import GovernActorBadge from "@/components/console/govern/primitives/GovernActorBadge.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernDataSourceChip from "@/components/console/govern/primitives/GovernDataSourceChip.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernEvidenceChip from "@/components/console/govern/primitives/GovernEvidenceChip.vue"
import GovernFilterBar from "@/components/console/govern/primitives/GovernFilterBar.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import GovernIdChip from "@/components/console/govern/primitives/GovernIdChip.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import GovernResultChip from "@/components/console/govern/primitives/GovernResultChip.vue"
import { formatGovernRelative, formatGovernStamp, formatGovernStampMillis, GOVERN_NOW } from "@/lib/govern-format"
import { auditEventHref, type AuditObjectState } from "@/lib/govern-query"
import {
  AUDIT_TARGET_TYPE_LABELS,
  auditActorSubline,
  auditIdempotencyAnswer,
  auditObjectEvents,
  auditObjectSummary,
  groupAuditEvents,
  type AuditEvent,
  type AuditTargetType,
} from "@/lib/audit-preview"

const props = defineProps<{ type: AuditTargetType; id: string; state: AuditObjectState }>()
const emit = defineEmits<{ update: [state: AuditObjectState] }>()

const about = ref<InstanceType<typeof GovernAboutPopover> | null>(null)

const summary = computed(() => auditObjectSummary(props.type, props.id))
const name = computed(() => summary.value.events[0]?.target.name ?? props.id)
const typeLabel = computed(() => AUDIT_TARGET_TYPE_LABELS[props.type])

const actionOptions = computed(() => {
  const actions = [...new Set(summary.value.events.map((event) => event.action))]
  return [{ value: "all", label: "All actions" }, ...actions.map((action) => ({ value: action, label: action }))]
})

const events = computed(() => {
  const actor = props.state.actor.trim().toLowerCase()
  return auditObjectEvents(props.type, props.id, props.state.failed)
    .filter((event) => !props.state.action || event.action === props.state.action)
    .filter((event) => !actor || event.actor.name.toLowerCase().includes(actor))
})

const groups = computed(() => groupAuditEvents(events.value))

function update(patch: Partial<AuditObjectState>): void {
  emit("update", { ...props.state, ...patch })
}

function clearFilters(): void {
  emit("update", { actor: "", action: "", failed: false })
}

function idempotency(event: AuditEvent): string {
  const answer = auditIdempotencyAnswer(event)
  return answer.detail
}
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
          <div class="mt-1.5 flex flex-wrap items-center gap-2">
            <span class="ix-preview-chip">{{ typeLabel }}</span>
            <GovernIdChip :value="id" label="Object ID" />
          </div>
          <h1 class="mt-1 ix-page-title text-fg-1">{{ name }}</h1>
          <p class="mt-1 max-w-2xl text-sm leading-5 text-fg-2">
            Every recorded change to this {{ typeLabel.toLowerCase() }}, newest first, with who made it and whether it
            was applied exactly once.
          </p>
        </div>

        <div class="flex shrink-0 flex-wrap items-center gap-2">
          <GovernDataSourceChip @open="about?.open()" />
      <GovernAboutPopover
        ref="about"
        verdict="This history is filtered from the recorded preview event set. The audit stream is not connected, so an empty history does not prove nothing happened."
        contract="operator.audit.list.v1"
        scope="org_demo_42 · workspace ws_42"
        range="Recorded preview events, 26–30 Oct 2026"
        coverage="Preview fixtures · no audit stream connected"
        phase="A3 · Phase B2"
        claim="No enforcement, billing, or deletion claim."
        :notes="[
          { lead: 'Only events that name this object appear.', body: 'The console matches on the recorded target type and ID. Events that mention the object in prose are not inferred into the timeline.' },
          { lead: 'Failed changes are hidden by default.', body: 'Turn on “Include failed” to see rejected, retrying, and dead-lettered attempts alongside applied changes.' },
        ]"
      />
          <GovernLockedAction label="Export history" :icon="Download" />
        </div>
      </div>

    </header>

    <dl class="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line-subtle bg-line-subtle sm:grid-cols-3">
      <div class="bg-surface-1 px-3 py-2.5">
        <dt class="text-[0.6875rem] text-fg-3">Events recorded</dt>
        <dd class="mt-0.5 font-mono text-sm font-semibold text-fg-1 tabular-nums">{{ summary.count }}</dd>
      </div>
      <div class="bg-surface-1 px-3 py-2.5">
        <dt class="text-[0.6875rem] text-fg-3">Applied</dt>
        <dd class="mt-0.5 font-mono text-sm font-semibold text-ok tabular-nums">{{ summary.applied }}</dd>
      </div>
      <div class="bg-surface-1 px-3 py-2.5">
        <dt class="text-[0.6875rem] text-fg-3">Failed or pending</dt>
        <dd class="mt-0.5 font-mono text-sm font-semibold tabular-nums" :class="summary.failed ? 'text-warn' : 'text-fg-2'">
          {{ summary.failed }}
        </dd>
      </div>
      <div class="bg-surface-1 px-3 py-2.5">
        <dt class="text-[0.6875rem] text-fg-3">Actors</dt>
        <dd class="mt-0.5 truncate text-xs text-fg-1" :title="summary.actors.join(', ')">
          {{ summary.actors.length ? summary.actors.join(", ") : "None recorded" }}
        </dd>
      </div>
      <div class="bg-surface-1 px-3 py-2.5">
        <dt class="text-[0.6875rem] text-fg-3">First event</dt>
        <dd class="mt-0.5 font-mono text-[0.6875rem] text-fg-2">
          {{ summary.firstAt ? formatGovernStamp(summary.firstAt) : "Not recorded" }}
        </dd>
      </div>
      <div class="bg-surface-1 px-3 py-2.5">
        <dt class="text-[0.6875rem] text-fg-3">Last event</dt>
        <dd class="mt-0.5 font-mono text-[0.6875rem] text-fg-2">
          {{ summary.lastAt ? formatGovernStamp(summary.lastAt) : "Not recorded" }}
        </dd>
      </div>
    </dl>

    <GovernFilterBar
      :model-value="state.actor"
      label="Filter by actor"
      placeholder="Filter by actor name"
      :result-text="`${events.length} of ${summary.count} events`"
      :active="Boolean(state.actor || state.action || state.failed)"
      @update:model-value="update({ actor: $event })"
      @clear="clearFilters"
    >
      <template #filters>
        <GovernFilterSelect
          label="Action"
          :model-value="state.action || 'all'"
          :options="actionOptions"
          default-value="all"
          @update:model-value="update({ action: $event === 'all' ? '' : $event })"
        />
        <button
          type="button"
          class="inline-flex h-8 items-center gap-1.5 rounded-full border px-2.5 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
          :class="state.failed ? 'border-warn/40 bg-warn-tint text-warn' : 'border-line-subtle bg-surface-1 text-fg-3 hover:border-line'"
          :aria-pressed="state.failed"
          @click="update({ failed: !state.failed })"
        >
          Include failed
        </button>
      </template>
      <template #right>
        <span class="inline-flex items-center gap-1.5">
          <History :size="12" :stroke-width="1.8" aria-hidden="true" />
          {{ state.failed ? "Applied and failed events" : "Applied events only" }}
        </span>
      </template>
    </GovernFilterBar>

    <GovernEmptyState
      v-if="events.length === 0"
      title="No events match this history view"
      :reason="
        summary.count === 0
          ? `No recorded event targets this ${typeLabel.toLowerCase()}. The preview set does not reconstruct missing history.`
          : 'Every recorded event for this object is filtered out by the current actor, action, or failed-event setting.'
      "
      next-step="Clear the filters, or include failed events to see rejected and retrying attempts."
      action-label="Clear filters"
      @action="clearFilters"
    />

    <div v-else class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
      <template v-for="group in groups" :key="group.key">
        <div class="border-b border-line-subtle bg-surface-2/70 px-3.5 py-1.5">
          <p class="text-[0.6875rem] font-medium tracking-wide text-fg-3 uppercase">
            {{ group.label }}
            <span class="ml-1.5 font-normal normal-case">· {{ group.events.length }} event{{ group.events.length === 1 ? "" : "s" }}</span>
          </p>
        </div>
        <ol class="relative">
          <li
            v-for="event in group.events"
            :key="event.id"
            class="relative flex min-w-0 gap-3 border-b border-line-subtle px-3.5 py-3 last:border-b-0"
          >
            <span
              class="absolute top-0 bottom-0 left-0 w-0.5"
              :class="event.result === 'dead_lettered' ? 'bg-crit' : event.result === 'retrying' ? 'bg-warn' : 'bg-transparent'"
              aria-hidden="true"
            />
            <div class="flex min-w-0 flex-1 flex-col gap-1.5">
              <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                <GovernActorBadge
                  :name="event.actor.name"
                  :type="event.actor.type"
                  :step-up="event.stepUp"
                  :subline="auditActorSubline(event)"
                  size="sm"
                />
                <span class="font-mono text-[0.6875rem] text-fg-3" :title="formatGovernStampMillis(event.at)">
                  {{ formatGovernRelative(event.at, GOVERN_NOW) }}
                </span>
                <GovernResultChip :result="event.result" />
                <GovernEvidenceChip :evidence="event.evidence" />
              </div>
              <div class="min-w-0">
                <NuxtLink
                  :to="auditEventHref(event.id)"
                  class="font-mono text-[0.6875rem] text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline"
                >
                  {{ event.action }}
                </NuxtLink>
                <p class="mt-0.5 text-xs leading-5 text-fg-2">{{ event.summary }}</p>
              </div>
              <p class="text-[0.6875rem] leading-4 text-fg-3">
                {{ idempotency(event) }}
                <span aria-hidden="true">·</span>
                <span class="font-mono">{{ event.id }}</span>
                <GovernCopyId :id="event.id" label="Event ID" icon-only />
              </p>
            </div>
            <NuxtLink
              :to="auditEventHref(event.id)"
              class="ix-row-action mt-0.5 inline-flex size-7 shrink-0 items-center justify-center rounded text-fg-3 hover:text-fg-1"
              :aria-label="`Open event ${event.id}`"
            >
              <span aria-hidden="true" class="text-base leading-none">›</span>
            </NuxtLink>
          </li>
        </ol>
      </template>
    </div>

    <p class="text-[0.6875rem] leading-4 text-fg-3">
      Applied and failed events are both shown above when enabled. Times show relative age; hover for the absolute time
      with milliseconds. Days are grouped in UTC.
    </p>
  </div>
</template>
