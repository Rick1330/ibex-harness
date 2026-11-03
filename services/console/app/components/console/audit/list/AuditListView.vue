<script setup lang="ts">
import { computed, ref } from "vue"
import { ArrowUp, ChevronRight, ShieldCheck, TriangleAlert } from "@lucide/vue"
import GovernActorBadge from "@/components/console/govern/primitives/GovernActorBadge.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernEvidenceChip from "@/components/console/govern/primitives/GovernEvidenceChip.vue"
import GovernFilterBar from "@/components/console/govern/primitives/GovernFilterBar.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import GovernPeekSheet from "@/components/console/govern/primitives/GovernPeekSheet.vue"
import GovernResultChip from "@/components/console/govern/primitives/GovernResultChip.vue"
import GovernShortcutsDialog from "@/components/console/govern/primitives/GovernShortcutsDialog.vue"
import AuditListHeader from "./AuditListHeader.vue"
import { useGovernShortcuts } from "@/composables/useGovernShortcuts"
import { useTriageTable } from "@/composables/useTriageTable"
import { formatGovernRelative, formatGovernStamp, formatGovernStampMillis, GOVERN_NOW } from "@/lib/govern-format"
import { AUDIT_LIST_DEFAULT, auditEventHref, auditListHref, type AuditListQueryState } from "@/lib/govern-query"
import {
  AUDIT_ORIGIN_LABELS,
  AUDIT_RANGE_LABELS,
  AUDIT_RESULT_LABELS,
  AUDIT_TARGET_TYPE_LABELS,
  AUDIT_PAGE_SIZE,
  auditAction,
  auditActorSubline,
  auditAttentionCounts,
  auditEvents,
  auditIdempotencyAnswer,
  auditObjectHref,
  auditPage,
  auditRangeEvents,
  auditTargetHref,
  filterAuditEvents,
  groupAuditEvents,
  type AuditEvent,
  type AuditOrigin,
  type AuditRange,
  type AuditResult,
  type AuditSavedViewId,
} from "@/lib/audit-preview"

const props = defineProps<{ state: AuditListQueryState }>()
const emit = defineEmits<{ update: [state: AuditListQueryState] }>()

function update(patch: Partial<AuditListQueryState>): void {
  const next = { ...props.state, ...patch }
  if (!("cursor" in patch)) next.cursor = null
  emit("update", next)
}

const header = ref<InstanceType<typeof AuditListHeader> | null>(null)
const search = ref<InstanceType<typeof GovernFilterBar> | null>(null)

const rangeEvents = computed(() => auditRangeEvents(props.state.range))
const attention = computed(() => auditAttentionCounts(rangeEvents.value))

const resultOptions = [
  { value: "all", label: "All results" },
  ...(Object.keys(AUDIT_RESULT_LABELS) as AuditResult[]).map((result) => ({
    value: result,
    label: AUDIT_RESULT_LABELS[result],
  })),
]

const originOptions = [
  { value: "all", label: "All origins" },
  ...(Object.keys(AUDIT_ORIGIN_LABELS) as AuditOrigin[]).map((origin) => ({
    value: origin,
    label: AUDIT_ORIGIN_LABELS[origin],
  })),
]

const filtered = computed(() => filterAuditEvents(auditEvents, props.state))
const rows = computed(() =>
  [...filtered.value].sort((left, right) => Date.parse(right.at) - Date.parse(left.at)),
)

const page = computed(() => auditPage(rows.value, props.state.cursor))
const groups = computed(() => groupAuditEvents(page.value.items))

const activeFilters = computed(
  () =>
    [
      props.state.query.trim(),
      props.state.view !== AUDIT_LIST_DEFAULT.view,
      props.state.result !== "all",
      props.state.origin !== "all",
    ].filter(Boolean).length,
)

const attentionTiles = computed(() => {
  const counts = attention.value
  const tiles: {
    key: string
    label: string
    count: number
    hint: string
    numberClass: string
    onClick: () => void
  }[] = []
  if (counts.retrying > 0) {
    tiles.push({
      key: "retrying",
      label: "Retrying",
      count: counts.retrying,
      hint: "Delivery is being retried; no effect yet.",
      numberClass: "text-warn",
      onClick: () => update({ view: "all", result: "retrying" }),
    })
  }
  if (counts.deadLettered > 0) {
    tiles.push({
      key: "dead-lettered",
      label: "Dead-lettered",
      count: counts.deadLettered,
      hint: "Retries were exhausted for these deliveries.",
      numberClass: "text-crit",
      onClick: () => update({ view: "all", result: "dead_lettered" }),
    })
  }
  if (counts.rejected > 0) {
    tiles.push({
      key: "rejected",
      label: "Rejected by policy",
      count: counts.rejected,
      hint: "Blocked before any effect was applied.",
      numberClass: "text-crit",
      onClick: () => update({ view: "all", result: "rejected" }),
    })
  }
  if (counts.privileged > 0) {
    tiles.push({
      key: "privileged",
      label: "Privileged (step-up)",
      count: counts.privileged,
      hint: "A re-authentication was required and recorded.",
      numberClass: "text-fg-1",
      onClick: () => update({ view: "privileged" }),
    })
  }
  return tiles
})

const showAttention = computed(() => attentionTiles.value.length > 0 || (attention.value.chainGaps ?? 0) > 0)

const peekId = ref<string | null>(null)
const peekOpen = ref(false)
const peekEvent = computed(() => page.value.items.find((event) => event.id === peekId.value) ?? null)

const triage = useTriageTable({
  rows: computed(() => page.value.items),
  enabled: () => !peekOpen.value,
  onOpen: (event) => void navigateTo(auditEventHref(event.id)),
  onPeek: (event) => {
    peekId.value = event.id
    peekOpen.value = true
  },
})

function clearFilters(): void {
  emit("update", { ...AUDIT_LIST_DEFAULT, cursor: null })
}

function loadOlder(): void {
  if (!page.value.nextCursor) return
  update({ cursor: Number(page.value.nextCursor) })
}

function backToNewest(): void {
  update({ cursor: null })
  if (!import.meta.client) return
  window.scrollTo({ top: 0, behavior: "smooth" })
}

function copyCurrentLink(): void {
  if (!import.meta.client) return
  void navigator.clipboard.writeText(`${window.location.origin}${auditListHref(props.state)}`)
}


function targetHref(event: AuditEvent): string {
  return auditTargetHref(event.target) ?? auditObjectHref(event.target.type, event.target.id)
}

const { helpOpen } = useGovernShortcuts({
  onSearch: () => search.value?.focus(),
  onEscape: () => {
    if (peekOpen.value) {
      peekOpen.value = false
      return
    }
    triage.select(null)
  },
  keys: { y: copyCurrentLink },
})

const shortcutGroups = [
  {
    title: "Move",
    rows: [
      { keys: "j / k", label: "Next / previous event" },
      { keys: "Enter", label: "Open the selected event" },
      { keys: "Space", label: "Open the 480px peek" },
      { keys: "/", label: "Focus search" },
      { keys: "Esc", label: "Close the peek or clear selection" },
    ],
  },
  {
    title: "This page",
    rows: [
      { keys: "y", label: "Copy link to this view" },
      { keys: "g p", label: "Go to policies" },
      { keys: "g d", label: "Go to drift" },
      { keys: "g a", label: "Go to audit log" },
      { keys: "?", label: "Show this sheet" },
    ],
  },
]
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">
    <AuditListHeader
      ref="header"
      :range="state.range"
      :view="state.view"
      @update:range="update({ range: $event as AuditRange })"
      @update:view="update({ view: $event as AuditSavedViewId })"
    />

    <section v-if="showAttention" class="flex flex-wrap items-center gap-2" aria-label="Needs attention">
      <span class="inline-flex items-center gap-1.5 text-[0.6875rem] font-medium text-fg-3">
        <TriangleAlert :size="12" :stroke-width="1.9" aria-hidden="true" />
        Needs attention
      </span>
      <button
        v-for="tile in attentionTiles"
        :key="tile.key"
        type="button"
        class="group inline-flex min-w-0 items-center gap-2 rounded-full border px-2.5 py-1 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        :class="
          (tile.key === 'retrying' && state.result === 'retrying') ||
          (tile.key === 'dead-lettered' && state.result === 'dead_lettered') ||
          (tile.key === 'rejected' && state.result === 'rejected') ||
          (tile.key === 'privileged' && state.view === 'privileged')
            ? 'border-accent/40 bg-accent-tint text-fg-1'
            : 'border-line-subtle bg-surface-1 text-fg-2 hover:border-line'
        "
        :title="tile.hint"
        @click="tile.onClick()"
      >
        <span class="font-mono text-sm leading-5 font-semibold tabular-nums" :class="tile.numberClass">{{ tile.count }}</span>
        <span class="whitespace-nowrap">{{ tile.label }}</span>
      </button>
      <NuxtLink
        v-if="(attention.chainGaps ?? 0) > 0"
        to="/audit/integrity"
        class="inline-flex items-center gap-2 rounded-full border border-crit/40 bg-crit-tint px-2.5 py-1 text-xs text-crit focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
      >
        <span class="font-mono text-sm leading-5 font-semibold tabular-nums">{{ attention.chainGaps }}</span>
        Chain gaps
      </NuxtLink>
      <NuxtLink
        to="/audit/integrity"
        class="ml-auto inline-flex items-center gap-1 text-[0.6875rem] text-fg-3 underline decoration-line-strong underline-offset-2 hover:text-fg-1"
      >
        <ShieldCheck :size="12" :stroke-width="1.8" aria-hidden="true" />
        Integrity &amp; retention
      </NuxtLink>
    </section>

    <GovernFilterBar
      ref="search"
      :model-value="state.query"
      label="Search audit events"
      placeholder="Search, or filter: actor:&quot;Jon Park&quot; action:directive.*"
      :result-text="`${rows.length} of ${rangeEvents.length} events`"
      :active="activeFilters > 0"
      @update:model-value="update({ query: $event })"
      @clear="clearFilters"
    >
      <template #filters>
        <GovernFilterSelect
          label="Result"
          :model-value="state.result"
          :options="resultOptions"
          default-value="all"
          @update:model-value="update({ result: $event as AuditResult | 'all' })"
        />
        <GovernFilterSelect
          label="Origin"
          :model-value="state.origin"
          :options="originOptions"
          default-value="all"
          @update:model-value="update({ origin: $event as AuditOrigin | 'all' })"
        />
      </template>
      <template #right>
        <span class="hidden lg:inline">
          Query:
          <code class="rounded bg-surface-2 px-1 py-0.5 font-mono text-[0.625rem] text-fg-2">actor:"Jon Park"</code>
          <code class="ml-1 rounded bg-surface-2 px-1 py-0.5 font-mono text-[0.625rem] text-fg-2">action:directive.*</code>
          <code class="ml-1 rounded bg-surface-2 px-1 py-0.5 font-mono text-[0.625rem] text-fg-2">result:rejected</code>
          <code class="ml-1 rounded bg-surface-2 px-1 py-0.5 font-mono text-[0.625rem] text-fg-2">origin:policy</code>
          <code class="ml-1 rounded bg-surface-2 px-1 py-0.5 font-mono text-[0.625rem] text-fg-2">step_up:true</code>
        </span>
      </template>
    </GovernFilterBar>

    <div v-if="rows.length === 0" class="rounded-lg border border-line-subtle bg-surface-1 p-2">
      <GovernEmptyState
        title="No audit events match these filters"
        :reason="`No recorded event in ${AUDIT_RANGE_LABELS[state.range].toLowerCase()} matches the current view and query.`"
        next-step="Clear the filters, or widen the time range to include older events."
        action-label="Clear filters"
        @action="clearFilters"
      />
    </div>

    <template v-else>
      <div class="ix-scroll overflow-x-auto rounded-lg border border-line-subtle">
        <table class="ix-agent-table table-fixed" style="min-width: 1162px" aria-label="Audit events">
          <thead>
            <tr>
              <th scope="col" style="width: 92px">Time</th>
              <th scope="col" style="width: 190px">Actor</th>
              <th scope="col" style="width: 210px">Action</th>
              <th scope="col" style="width: 250px">Target</th>
              <th scope="col" style="width: 100px">Origin</th>
              <th scope="col" style="width: 110px">Result</th>
              <th scope="col" style="width: 100px">Evidence</th>
              <th scope="col" style="width: 78px" class="text-right">
                <span title="Fields removed before the audit record was written">Redactions</span>
              </th>
              <th scope="col" style="width: 32px; padding-right: 0.25rem"><span class="sr-only">Open</span></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="group in groups" :key="group.key">
              <tr class="bg-surface-2/60">
                <th scope="colgroup" colspan="9" class="px-3 py-1.5 text-left text-[0.6875rem] font-medium text-fg-3">
                  {{ group.label }}
                  <span class="ml-1.5 font-normal normal-case">· {{ group.events.length }} event{{ group.events.length === 1 ? "" : "s" }}</span>
                </th>
              </tr>
              <tr v-for="event in group.events" :key="event.id" v-bind="triage.rowAttrs(event)">
                <td class="relative">
                  <span class="font-mono text-[0.6875rem] whitespace-nowrap text-fg-2 tabular-nums" :title="formatGovernStampMillis(event.at)">
                    {{ formatGovernRelative(event.at, GOVERN_NOW) }}
                  </span>
                </td>
                <td>
                  <GovernActorBadge
                    :name="event.actor.name"
                    :type="event.actor.type"
                    :step-up="event.stepUp"
                    :subline="auditActorSubline(event)"
                    size="sm"
                  />
                </td>
                <td>
                  <NuxtLink
                    :to="auditEventHref(event.id)"
                    class="block max-w-full truncate font-mono text-[0.6875rem] leading-4 text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline"
                  >
                    {{ event.action }}
                  </NuxtLink>
                  <span class="mt-0.5 block max-w-full truncate text-[0.6875rem] leading-4 text-fg-3" :title="event.summary">
                    {{ event.summary }}
                  </span>
                </td>
                <td>
                  <NuxtLink
                    :to="targetHref(event)"
                    class="block max-w-full truncate text-xs text-fg-2 underline decoration-line-strong underline-offset-2 hover:text-fg-1"
                    :title="event.target.name"
                  >
                    {{ event.target.name }}
                  </NuxtLink>
                  <span class="mt-0.5 block truncate font-mono text-[0.625rem] leading-4 text-fg-3" :title="`${event.target.type} · ${event.target.id}`">
                    {{ AUDIT_TARGET_TYPE_LABELS[event.target.type] }} · {{ event.target.id }}
                  </span>
                </td>
                <td class="text-xs whitespace-nowrap text-fg-2">{{ AUDIT_ORIGIN_LABELS[event.origin] }}</td>
                <td><GovernResultChip :result="event.result" /></td>
                <td><GovernEvidenceChip :evidence="event.evidence" /></td>
                <td class="text-right">
                  <span
                    v-if="event.request.redactions.length"
                    class="inline-flex h-5 min-w-5 items-center justify-center rounded-full border border-warn/30 bg-warn-tint px-1.5 font-mono text-[0.625rem] font-medium text-warn tabular-nums"
                    :title="event.request.redactions.map((item) => `${item.field}: ${item.reason}`).join(' · ')"
                  >
                    {{ event.request.redactions.length }}
                  </span>
                  <span v-else class="text-xs text-fg-off">—</span>
                </td>
                <td style="padding-left: 0.25rem; padding-right: 0">
                  <NuxtLink
                    :to="auditEventHref(event.id)"
                    class="ix-row-action inline-flex size-7 items-center justify-center rounded text-fg-3 hover:text-fg-1"
                    :aria-label="`Open event ${event.id}`"
                  >
                    <ChevronRight :size="14" :stroke-width="1.9" aria-hidden="true" />
                  </NuxtLink>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <div class="sticky bottom-3 z-10 flex justify-center">
        <button
          v-if="page.loaded > AUDIT_PAGE_SIZE"
          type="button"
          class="inline-flex h-8 items-center gap-1.5 rounded-full border border-line bg-overlay px-3 text-xs font-medium text-fg-2 shadow-lg transition-colors hover:border-line-strong hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
          @click="backToNewest"
        >
          <ArrowUp :size="13" :stroke-width="1.9" aria-hidden="true" />
          Back to newest
        </button>
      </div>

      <div class="flex flex-wrap items-center justify-between gap-2">
        <p class="text-[0.6875rem] leading-4 text-fg-3">
          Showing {{ page.loaded }} of {{ page.total }} events in range · newest first · days grouped in UTC.
          Times show relative age; hover for the absolute time with milliseconds.
        </p>
        <button
          v-if="page.hasMore"
          type="button"
          class="ix-button-secondary h-8 px-3 text-xs"
          @click="loadOlder"
        >
          Load {{ Math.min(AUDIT_PAGE_SIZE, page.total - page.loaded) }} older
        </button>
        <span v-else class="text-[0.6875rem] text-fg-3">End of recorded events.</span>
      </div>
    </template>

    <GovernPeekSheet
      v-if="peekEvent"
      v-model:open="peekOpen"
      :title="peekEvent.action"
      :description="`${peekEvent.actor.name} · ${formatGovernStamp(peekEvent.at)}`"
      :href="auditEventHref(peekEvent.id)"
      href-label="Open the full event"
    >
      <div class="flex flex-col gap-3">
        <div class="flex flex-wrap items-center gap-2">
          <GovernResultChip :result="peekEvent.result" />
          <GovernEvidenceChip :evidence="peekEvent.evidence" />
          <span class="text-xs text-fg-3">{{ AUDIT_ORIGIN_LABELS[peekEvent.origin] }}</span>
        </div>

        <p class="text-sm leading-6 text-fg-2">{{ peekEvent.summary }}</p>

        <div class="rounded-lg border border-line-subtle bg-surface-2 px-3 py-2.5">
          <p class="text-xs font-medium text-fg-1">{{ auditIdempotencyAnswer(peekEvent).label }}</p>
          <p class="mt-0.5 text-xs leading-4 text-fg-3">{{ auditIdempotencyAnswer(peekEvent).detail }}</p>
          <p class="mt-1 font-mono text-[0.625rem] leading-4 text-fg-3">
            {{ peekEvent.idempotency.key }}
          </p>
        </div>

        <dl class="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line-subtle bg-line-subtle">
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Actor</dt>
            <dd class="mt-0.5 text-xs text-fg-1">{{ peekEvent.actor.name }}</dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Occurred</dt>
            <dd class="mt-0.5 font-mono text-[0.6875rem] text-fg-2" :title="formatGovernStampMillis(peekEvent.at)">
              {{ formatGovernStamp(peekEvent.at) }}
            </dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Target</dt>
            <dd class="mt-0.5 truncate text-xs text-fg-1" :title="peekEvent.target.name">{{ peekEvent.target.name }}</dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Request</dt>
            <dd class="mt-0.5 truncate font-mono text-[0.6875rem] text-fg-2" :title="`${peekEvent.request.method} ${peekEvent.request.route}`">
              {{ peekEvent.request.method }} {{ peekEvent.request.route }} · {{ peekEvent.request.status }}
            </dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Policy</dt>
            <dd class="mt-0.5 font-mono text-[0.6875rem] text-fg-2">{{ peekEvent.policy?.decision ?? "—" }}</dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Retry</dt>
            <dd class="mt-0.5 text-[0.6875rem] text-fg-2">{{ peekEvent.retry?.reason ?? "—" }}</dd>
          </div>
        </dl>

        <p class="text-[0.6875rem] leading-4 text-fg-3">
          {{ auditAction(peekEvent.action).sentence }}.
        </p>

        <NuxtLink :to="auditEventHref(peekEvent.id)" class="ix-button-secondary h-8 w-fit px-3 text-xs">
          Open event
        </NuxtLink>
      </div>
    </GovernPeekSheet>

    <GovernShortcutsDialog v-model:open="helpOpen" :groups="shortcutGroups" />
  </div>
</template>
