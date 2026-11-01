<script setup lang="ts">
import { computed, ref } from "vue"
import { ArrowLeft, Download, FileClock, ShieldCheck } from "@lucide/vue"
import GovernAboutPopover from "@/components/console/govern/primitives/GovernAboutPopover.vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernDataSourceChip from "@/components/console/govern/primitives/GovernDataSourceChip.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import GovernPendingData from "@/components/console/govern/primitives/GovernPendingData.vue"
import { formatGovernNumber } from "@/lib/govern-format"
import type { AuditIntegrityState } from "@/lib/govern-query"
import {
  AUDIT_EXPORT_FORMATS,
  AUDIT_EXPORT_LOCK_REASON,
  AUDIT_INTEGRITY_CONTRACT,
  AUDIT_INTEGRITY_PENDING,
  AUDIT_RANGES,
  AUDIT_RANGE_LABELS,
  auditExportBoundary,
  auditExportHistory,
  auditRangeEvents,
  auditRetention,
  type AuditRange,
} from "@/lib/audit-preview"

const props = defineProps<{ state: AuditIntegrityState }>()
const emit = defineEmits<{ update: [state: AuditIntegrityState] }>()

const about = ref<InstanceType<typeof GovernAboutPopover> | null>(null)

const rangeOptions = AUDIT_RANGES.map((range) => ({ value: range, label: AUDIT_RANGE_LABELS[range] }))
const formatOptions = AUDIT_EXPORT_FORMATS.map((format) => ({ value: format, label: format }))
const boundary = computed(() => auditExportBoundary(auditRangeEvents(props.state.range)))
const history = auditExportHistory

function update(patch: Partial<AuditIntegrityState>): void {
  emit("update", { ...props.state, ...patch })
}

function setFormat(value: string): void {
  update({ format: value as AuditIntegrityState["format"] })
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
          <div class="mt-1.5 flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
            <h1 class="ix-page-title text-fg-1">Audit integrity</h1>
                      </div>
          <p class="mt-1 max-w-2xl text-sm leading-5 text-fg-2">
            Whether the recorded chain is complete, how long records are kept, and what an export would include.
          </p>
        </div>

        <div class="flex shrink-0 flex-wrap items-center gap-2">
          <GovernDataSourceChip @open="about?.open()" />
      <GovernAboutPopover
        ref="about"
        verdict="No integrity check is connected. The console shows the pending contract, the recorded retention policy, and the boundary an export would cover — nothing is verified here."
        contract="operator.audit.integrity.v1"
        scope="org_demo_42 · workspace ws_42"
        range="Recorded preview events, 26–30 Oct 2026"
        coverage="Preview fixtures · integrity and export not connected"
        phase="A3 · Phase B2"
        retention="7 years · workspace data agreement, section 4"
        claim="No enforcement, billing, or deletion claim."
        :notes="[
          { lead: 'Pending is not passing.', body: 'A missing verification result is shown as “Not reported yet”. The console never turns an absent check into a green state.' },
          { lead: 'Retention is a policy value.', body: 'The retention shown here comes from the workspace agreement. It is not proof that every record is present for that period.' },
          { lead: 'Export unlocks with two contracts.', body: 'A signed export needs operator.audit.export.v1 plus a defined completeness boundary and access-control rule.' },
        ]"
      />
          <GovernLockedAction label="Export audit log" :icon="Download" />
        </div>
      </div>

    </header>

    <div class="grid gap-3 xl:grid-cols-[minmax(0,1fr)_20rem]">
      <section class="rounded-lg border border-line-subtle bg-surface-1 p-3.5" aria-labelledby="integrity-check">
        <div class="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 id="integrity-check" class="flex items-center gap-1.5 text-sm font-semibold text-fg-1">
              <ShieldCheck :size="15" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
              Chain verification
            </h2>
            <p class="mt-0.5 max-w-[60ch] text-xs leading-4 text-fg-3">
              A complete check would confirm sequence continuity, hash linkage, and that no late event was silently dropped.
            </p>
          </div>
          <span class="ix-preview-chip border-transparent text-warn">Not connected</span>
        </div>

        <div class="mt-3">
          <GovernPendingData
            title="Integrity verification"
            :contract="AUDIT_INTEGRITY_CONTRACT"
            :description="AUDIT_INTEGRITY_PENDING"
          />
        </div>

        <ul class="mt-3 grid gap-px overflow-hidden rounded-lg border border-line-subtle bg-line-subtle sm:grid-cols-3">
          <li class="bg-surface-1 px-3 py-2">
            <p class="text-[0.6875rem] text-fg-3">Sequence gaps</p>
            <p class="mt-0.5 text-xs text-fg-2">Not reported yet</p>
          </li>
          <li class="bg-surface-1 px-3 py-2">
            <p class="text-[0.6875rem] text-fg-3">Hash linkage</p>
            <p class="mt-0.5 text-xs text-fg-2">Not reported yet</p>
          </li>
          <li class="bg-surface-1 px-3 py-2">
            <p class="text-[0.6875rem] text-fg-3">Late arrivals</p>
            <p class="mt-0.5 text-xs text-fg-2">Not reported yet</p>
          </li>
        </ul>
      </section>

      <section class="rounded-lg border border-line-subtle bg-surface-1 p-3.5" aria-labelledby="audit-retention">
        <h2 id="audit-retention" class="flex items-center gap-1.5 text-sm font-semibold text-fg-1">
          <FileClock :size="15" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
          Retention
        </h2>
        <p class="mt-1 font-mono text-2xl leading-8 font-semibold text-fg-1">{{ auditRetention.label }}</p>
        <p class="mt-0.5 text-xs leading-4 text-fg-2">{{ auditRetention.source }}</p>
        <p class="mt-2 text-[0.6875rem] leading-4 text-fg-3">
          One value for the workspace. The console does not compute retention from the sample events on this page.
        </p>
      </section>
    </div>

    <section class="rounded-lg border border-line-subtle bg-surface-1" aria-labelledby="audit-export">
      <div class="flex flex-wrap items-start justify-between gap-2 border-b border-line-subtle px-3.5 py-3">
        <div>
          <h2 id="audit-export" class="text-sm font-semibold text-fg-1">Export</h2>
          <p class="mt-0.5 text-xs leading-4 text-fg-3">
            A signed export must state exactly which events it covers. The boundary below is computed from the preview set.
          </p>
        </div>
        <span class="ix-preview-chip border-transparent text-warn">Locked</span>
      </div>

      <div class="grid gap-3 px-3.5 py-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div class="flex flex-col gap-2">
          <GovernFilterSelect
            label="Range"
            :model-value="state.range"
            :options="rangeOptions"
            default-value="7d"
            @update:model-value="update({ range: $event as AuditRange })"
          />
          <GovernFilterSelect
            label="Format"
            :model-value="state.format"
            :options="formatOptions"
            default-value="Signed NDJSON"
            @update:model-value="setFormat"
          />
          <p class="mt-1 font-mono text-[0.6875rem] leading-4 text-fg-3">
            {{ formatGovernNumber(boundary.count) }} events · {{ state.format }}
          </p>
        </div>

        <div class="flex flex-col gap-2">
          <GovernCaveat tone="lock" title="Completeness boundary">
            {{ boundary.text }}
          </GovernCaveat>
          <GovernCaveat tone="warning" title="Locked">
            {{ AUDIT_EXPORT_LOCK_REASON }}
          </GovernCaveat>
          <div class="mt-1">
            <GovernLockedAction label="Export" :icon="Download" />
          </div>
        </div>
      </div>
    </section>

    <section class="flex flex-col gap-2" aria-labelledby="past-exports">
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="past-exports" class="text-sm font-semibold text-fg-1">Past exports</h2>
        <span class="text-[0.6875rem] text-fg-3">Signed files, who requested them, and the hash of each</span>
      </div>

      <div v-if="history.length === 0" class="rounded-lg border border-line-subtle bg-surface-1 p-2">
        <GovernEmptyState
          title="No exports yet"
          reason="No export has been generated for this workspace, so there is no signed file or hash to show."
          next-step="Exports unlock when operator.audit.export.v1 ships with a completeness boundary and access-control contract."
        />
      </div>
      <div v-else class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
        <table class="ix-agent-table" aria-label="Past exports">
          <thead>
            <tr>
              <th scope="col">Export</th>
              <th scope="col">Requested by</th>
              <th scope="col">Range</th>
              <th scope="col">Hash</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entry in history" :key="entry.id">
              <td class="font-mono text-xs">{{ entry.id }}</td>
              <td class="text-xs">{{ entry.actor }}</td>
              <td class="text-xs">{{ entry.range }}</td>
              <td class="font-mono text-xs">{{ entry.hash }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
