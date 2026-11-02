<script setup lang="ts">
import { computed } from "vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import { formatGovernNumber, formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"
import type {
  ErasureStatus,
  OperatorEvidenceDeletions,
  ReceiptStatus,
} from "~~/shared/operator/contracts"

const props = defineProps<{ deletions: OperatorEvidenceDeletions | null, error: string | null }>()

const tombstones = computed(() => props.deletions?.tombstones ?? null)
const audit = computed(() => props.deletions?.audit ?? null)
const clock = computed(() => props.deletions?.observed_at ?? null)

const events = computed(() => {
  const counts = tombstones.value?.events
  if (!counts) return 0
  return counts.forgotten + counts.expired + counts.purged
})

const failedReceipts = computed(
  () =>
    props.deletions?.jobs.reduce(
      (sum, job) => sum + job.receipts.filter((receipt) => receipt.status === "failed").length,
      0,
    ) ?? 0,
)

const ERASURE_LABELS: Record<ErasureStatus, string> = {
  pending: "Queued",
  running: "Running",
  succeeded: "Succeeded",
  failed: "Failed",
  hold_blocked: "Hold blocked",
}

const ERASURE_TONE: Record<ErasureStatus, string> = {
  pending: "text-fg-2",
  running: "text-fg-2",
  succeeded: "text-ok",
  failed: "text-crit",
  hold_blocked: "text-warn",
}

const RECEIPT_LABELS: Record<ReceiptStatus, string> = {
  pending: "Pending",
  verified: "Verified absent",
  failed: "Failed",
  not_applicable: "Not applicable",
}

const RECEIPT_TONE: Record<ReceiptStatus, string> = {
  pending: "text-fg-3",
  verified: "text-ok",
  failed: "text-crit",
  not_applicable: "text-fg-3",
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <div v-if="!deletions" class="rounded-lg border border-dashed border-line-subtle bg-surface-1/40 px-4 py-6 text-center text-xs text-fg-3">
      {{ error ?? "The deletion record could not be read for this window." }}
    </div>

    <template v-else-if="deletions">
      <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4">
        <GovernStatTile
          label="Tombstoned in window"
          :value="formatGovernNumber(events)"
          helper="Forgotten, expired, or purged"
        />
        <GovernStatTile
          label="Propagation pending"
          :value="formatGovernNumber(tombstones?.pending ?? 0)"
          :helper="tombstones?.oldest_pending_at ? `Oldest ${formatGovernRelative(tombstones.oldest_pending_at, clock)}` : 'Every lifecycle event delivered'"
          :tone="(tombstones?.pending ?? 0) > 0 ? 'warning' : 'default'"
        />
        <GovernStatTile
          label="Tombstone fence"
          :value="formatGovernNumber(tombstones?.tombstoned_memories ?? 0)"
          helper="Records invisible to every retrieval mode now"
        />
        <GovernStatTile
          label="Erasures needing attention"
          :value="formatGovernNumber(deletions.erasures.failed + deletions.erasures.hold_blocked)"
          helper="Failed or blocked by a legal hold"
          :tone="deletions.erasures.failed + deletions.erasures.hold_blocked > 0 ? 'critical' : 'default'"
        />
      </div>

      <div class="console-panel p-3">
        <p class="text-xs font-medium text-fg-2">Lifecycle events in the window</p>
        <ul class="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-[0.6875rem] leading-4 text-fg-3">
          <li>
            Forgotten
            <span class="ml-1 font-mono tabular-nums text-fg-1">{{ formatGovernNumber(tombstones?.events.forgotten ?? 0) }}</span>
          </li>
          <li>
            Expired
            <span class="ml-1 font-mono tabular-nums text-fg-1">{{ formatGovernNumber(tombstones?.events.expired ?? 0) }}</span>
          </li>
          <li>
            Purged
            <span class="ml-1 font-mono tabular-nums text-fg-1">{{ formatGovernNumber(tombstones?.events.purged ?? 0) }}</span>
          </li>
          <li v-if="tombstones?.last_event_at">
            Newest {{ formatGovernRelative(tombstones.last_event_at, clock) }}
          </li>
        </ul>
      </div>

      <div class="console-panel p-3">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <p class="text-xs font-medium text-fg-2">Erasure jobs</p>
          <p class="text-[0.6875rem] text-fg-3">
            {{ deletions.jobs_truncated ? "Latest 20 in the window" : `${deletions.jobs.length} in the window` }}
          </p>
        </div>
        <ul v-if="deletions.jobs.length" class="mt-2 flex flex-col gap-2">
          <li v-for="job in deletions.jobs" :key="job.id" class="rounded-lg border border-line-subtle p-2">
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.6875rem]">
              <span class="font-mono text-fg-3">{{ job.id.slice(0, 8) }}…</span>
              <span :class="ERASURE_TONE[job.status]">{{ ERASURE_LABELS[job.status] }}</span>
              <span class="text-fg-3" :title="formatGovernStamp(job.created_at)">
                created {{ formatGovernRelative(job.created_at, clock) }}
              </span>
              <span v-if="job.finished_at" class="text-fg-3">
                finished {{ formatGovernRelative(job.finished_at, clock) }}
              </span>
            </div>
            <div class="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[0.625rem] leading-4">
              <span v-for="receipt in job.receipts" :key="receipt.store" class="inline-flex items-center gap-1">
                <span class="text-fg-3">{{ receipt.store }}</span>
                <span :class="RECEIPT_TONE[receipt.status]">{{ RECEIPT_LABELS[receipt.status] }}</span>
              </span>
              <span v-if="!job.receipts.length" class="text-fg-3">No store receipt recorded</span>
            </div>
          </li>
        </ul>
        <p v-else class="mt-2 text-xs text-fg-3">No erasure job in this window.</p>
      </div>

      <div class="console-panel p-3">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <p class="text-xs font-medium text-fg-2">Audit chain</p>
          <p class="text-[0.6875rem]" :class="audit?.continuity_ok ? 'text-ok' : 'text-crit'">
            {{ audit?.continuity_ok ? "Continuity intact" : `Broken at seq ${audit?.broken_at_seq}` }}
          </p>
        </div>
        <ul class="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-[0.6875rem] leading-4 text-fg-3">
          <li>
            Entries
            <span class="ml-1 font-mono tabular-nums text-fg-1">{{ formatGovernNumber(audit?.entries ?? 0) }}</span>
          </li>
          <li v-if="audit?.first_seq !== null && audit?.first_seq !== undefined">
            Seq <span class="font-mono tabular-nums text-fg-1">{{ audit.first_seq }}–{{ audit.last_seq }}</span>
          </li>
          <li v-if="audit?.last_row_hash" class="font-mono text-fg-3">
            head {{ audit.last_row_hash.slice(0, 12) }}…
          </li>
        </ul>
      </div>

      <GovernCaveat tone="info" title="Continuity is not content verification">
        This checks that the ledger has no gaps and that every entry links to the one before it. Re-deriving each entry's
        hash from its payload is the job of the <code>privacy-audit-verify</code> CLI on the host; doing it here would
        duplicate the canonicalisation in a second language.
      </GovernCaveat>
      <GovernCaveat v-if="failedReceipts > 0" tone="warning" title="A store has not confirmed the erasure">
        {{ formatGovernNumber(failedReceipts) }} store receipt(s) failed. The erasure is not complete until every
        deployed store reports <em>verified absent</em>; the job stays visible here rather than being retried silently.
      </GovernCaveat>
    </template>
  </div>
</template>
