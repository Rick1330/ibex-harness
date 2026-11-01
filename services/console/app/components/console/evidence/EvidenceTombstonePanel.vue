<script setup lang="ts">
import { computed, ref } from "vue"
import { Check, CircleSlash, Clock, ShieldCheck } from "@lucide/vue"
import GovernActorBadge from "@/components/console/govern/primitives/GovernActorBadge.vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernPeekSheet from "@/components/console/govern/primitives/GovernPeekSheet.vue"
import { formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"
import {
  DELETION_BASIS_LABELS,
  DOWNSTREAM_STATE_LABELS,
  TOMBSTONE_SUBJECT_LABELS,
  tombstoneChainComplete,
  tombstoneHistoryHref,
  tombstoneOpenSteps,
  type DownstreamState,
  type Tombstone,
} from "@/lib/evidence-preview"

const props = defineProps<{ rows: Tombstone[] }>()

const DOWNSTREAM_STEPS = [
  { key: "postgres", label: "Primary row" },
  { key: "search_index", label: "Vector index" },
  { key: "clickhouse", label: "Analytics" },
  { key: "archive", label: "Archive" },
] as const

const STATE_CLASS: Record<DownstreamState, string> = {
  applied: "text-ok",
  pending: "text-warn",
  failed: "text-crit",
  not_required: "text-fg-3",
}

const open = ref(false)
const selected = ref<Tombstone | null>(null)

function peek(tombstone: Tombstone): void {
  selected.value = tombstone
  open.value = true
}

const completed = computed(() => props.rows.filter(tombstoneChainComplete).length)

const selectedHref = computed(() => (selected.value ? tombstoneHistoryHref(selected.value) : null))

const viewRows = computed(() =>
  props.rows.map((tombstone) => ({ tombstone, href: tombstoneHistoryHref(tombstone) })),
)
</script>

<template>
  <div class="flex flex-col gap-3">
    <GovernCaveat tone="info" :title="`${completed} of ${rows.length} tombstones are fully applied`">
      A tombstone is only certified once every downstream step has reported back. Pending and failed steps stay visible
      here rather than being averaged into a single "deleted" flag.
    </GovernCaveat>

    <div v-if="rows.length === 0" class="rounded-lg border border-line-subtle bg-surface-1 p-2">
      <GovernEmptyState
        title="No tombstones in this view"
        reason="No recorded deletion matches the current basis, chain filter, or search."
        next-step="Clear the filters, or widen the range to include deletions from earlier days."
      />
    </div>

    <div v-else class="ix-scroll overflow-x-auto rounded-lg border border-line-subtle">
      <table class="ix-agent-table table-fixed" style="min-width: 1040px" aria-label="Tombstones">
        <thead>
          <tr>
            <th scope="col" style="width: 210px">Record</th>
            <th scope="col" style="width: 180px">Basis</th>
            <th scope="col" style="width: 110px">Deleted</th>
            <th scope="col" style="width: 170px">Requested by</th>
            <th scope="col" style="width: 110px">Tombstone</th>
            <th scope="col" style="width: 260px">Downstream</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="{ tombstone, href } in viewRows"
            :key="tombstone.id"
            tabindex="0"
            class="cursor-pointer"
            @click="peek(tombstone)"
            @keydown.enter.prevent="peek(tombstone)"
            @keydown.space.prevent="peek(tombstone)"
          >
            <td>
              <NuxtLink
                v-if="href"
                :to="href"
                class="block truncate text-xs text-fg-1 underline decoration-line-strong underline-offset-2 hover:text-accent-memory"
                :title="`History for ${tombstone.subjectName}`"
                @click.stop
              >
                {{ tombstone.subjectName }}
              </NuxtLink>
              <p v-else class="block truncate text-xs text-fg-1" :title="tombstone.subjectName">{{ tombstone.subjectName }}</p>
              <p class="mt-0.5 truncate font-mono text-[0.625rem] leading-4 text-fg-3">
                {{ TOMBSTONE_SUBJECT_LABELS[tombstone.subjectType] }} · {{ tombstone.id }}
              </p>
            </td>
            <td class="text-xs text-fg-2">{{ DELETION_BASIS_LABELS[tombstone.basis] }}</td>
            <td>
              <span class="font-mono text-[0.6875rem] whitespace-nowrap text-fg-2" :title="formatGovernStamp(tombstone.deletedAt)">
                {{ formatGovernRelative(tombstone.deletedAt) }}
              </span>
            </td>
            <td>
              <GovernActorBadge :name="tombstone.requestedBy" :type="tombstone.requestedByType" size="sm" />
            </td>
            <td>
              <span
                v-if="tombstone.tombstoneCertified"
                class="inline-flex items-center gap-1 text-xs text-ok"
                title="The tombstone row itself is certified and hash-chained into the audit log."
              >
                <ShieldCheck :size="12" :stroke-width="1.9" aria-hidden="true" />
                Certified
              </span>
              <span v-else class="inline-flex items-center gap-1 text-xs text-warn" title="No evidence row backs this deletion yet.">
                <CircleSlash :size="12" :stroke-width="1.9" aria-hidden="true" />
                Uncertified
              </span>
            </td>
            <td>
              <span class="flex flex-wrap gap-x-3 gap-y-1">
                <span
                  v-for="step in DOWNSTREAM_STEPS"
                  :key="step.key"
                  class="inline-flex items-center gap-1 text-[0.6875rem] whitespace-nowrap"
                  :class="STATE_CLASS[tombstone.downstream[step.key]]"
                  :title="`${step.label}: ${DOWNSTREAM_STATE_LABELS[tombstone.downstream[step.key]]}`"
                >
                  <Check v-if="tombstone.downstream[step.key] === 'applied'" :size="11" :stroke-width="2.2" aria-hidden="true" />
                  <Clock v-else-if="tombstone.downstream[step.key] === 'pending'" :size="11" :stroke-width="2.2" aria-hidden="true" />
                  <CircleSlash v-else :size="11" :stroke-width="2.2" aria-hidden="true" />
                  {{ step.label }}
                </span>
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <GovernPeekSheet
      v-if="selected"
      v-model:open="open"
      :title="selected.subjectName"
      :description="`${DELETION_BASIS_LABELS[selected.basis]} · ${formatGovernStamp(selected.deletedAt)}`"
    >
      <div class="flex flex-col gap-3">
        <div class="rounded-lg border border-line-subtle bg-surface-2 px-3 py-2.5">
          <p class="text-xs font-medium text-fg-1">
            {{ tombstoneChainComplete(selected) ? "Deletion fully applied" : `${tombstoneOpenSteps(selected).length} downstream step(s) still open` }}
          </p>
          <p class="mt-0.5 text-xs leading-4 text-fg-3">
            {{ selected.tombstoneCertified
              ? "The tombstone row is certified and chained into the audit log."
              : "No evidence row backs this deletion yet, so it cannot be presented as complete." }}
          </p>
          <GovernCopyId :id="selected.id" label="Tombstone id" class="mt-1.5" />
        </div>

        <dl class="flex flex-col gap-px overflow-hidden rounded-lg border border-line-subtle bg-line-subtle">
          <div v-for="step in DOWNSTREAM_STEPS" :key="step.key" class="flex items-center justify-between gap-3 bg-surface-1 px-3 py-2">
            <dt class="text-xs text-fg-2">{{ step.label }}</dt>
            <dd class="text-xs font-medium" :class="STATE_CLASS[selected.downstream[step.key]]">
              {{ DOWNSTREAM_STATE_LABELS[selected.downstream[step.key]] }}
            </dd>
          </div>
        </dl>

        <p v-if="selected.archiveNote" class="text-[0.6875rem] leading-4 text-fg-3">{{ selected.archiveNote }}</p>

        <p class="text-[0.6875rem] leading-4 text-fg-3">
          Requested by {{ selected.requestedBy }} · {{ formatGovernStamp(selected.deletedAt) }}
        </p>

        <NuxtLink
          v-if="selected && selectedHref"
          :to="selectedHref"
          class="ix-button-secondary h-8 w-fit px-3 text-xs"
        >
          Open the record's history
        </NuxtLink>
      </div>
    </GovernPeekSheet>
  </div>
</template>
