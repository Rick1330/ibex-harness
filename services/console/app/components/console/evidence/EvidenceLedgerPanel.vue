<script setup lang="ts">
import { computed } from "vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import { formatGovernNumber, formatGovernPercent, formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"
import {
  CAPTURE_MODE_LABELS,
  EVIDENCE_TIER_LABELS,
  EVIDENCE_TIER_MEANING,
  EVIDENCE_TIERS,
  evidenceCoverage,
  evidenceProducerTotal,
  evidenceTierPercent,
  type EvidenceProducerRow,
  type EvidenceTier,
} from "@/lib/evidence-preview"

const props = defineProps<{ rows: EvidenceProducerRow[]; selected: string }>()
const emit = defineEmits<{ select: [component: string] }>()

const TIER_BAR_CLASS: Record<EvidenceTier, string> = {
  evidence: "bg-ok",
  metadata: "bg-fg-3",
  redacted: "bg-s3",
  uncertified: "bg-warn",
  unavailable: "bg-crit",
}

const TIER_TEXT_CLASS: Record<EvidenceTier, string> = {
  evidence: "text-ok",
  metadata: "text-fg-2",
  redacted: "text-s3",
  uncertified: "text-warn",
  unavailable: "text-crit",
}

const coverage = computed(() => evidenceCoverage(props.rows))

function toggle(row: EvidenceProducerRow): void {
  emit("select", props.selected === row.id ? "all" : row.id)
}

function totalPercent(tier: EvidenceTier): number {
  if (!coverage.value.records) return 0
  return (coverage.value.totals[tier] / coverage.value.records) * 100
}

function tierMixLabel(row: EvidenceProducerRow): string {
  return EVIDENCE_TIERS.map(
    (tier) => `${EVIDENCE_TIER_LABELS[tier]} ${formatGovernPercent(evidenceTierPercent(row, tier), 0)}`,
  ).join(", ")
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
      <GovernStatTile
        label="Records in window"
        :value="formatGovernNumber(coverage.records)"
        helper="Across all producers and tiers"
      />
      <GovernStatTile
        label="Re-provable by digest"
        :value="formatGovernPercent(coverage.certifiedPercent)"
        :helper="`${formatGovernNumber(coverage.totals.evidence)} evidence rows`"
        tone="success"
      />
      <GovernStatTile
        label="Redacted before storage"
        :value="formatGovernNumber(coverage.totals.redacted)"
        helper="Fields removed, metadata kept"
        tone="warning"
      />
      <GovernStatTile
        label="Observed, nothing behind it"
        :value="formatGovernNumber(coverage.totals.uncertified)"
        helper="Includes every derived projection"
        tone="warning"
      />
      <GovernStatTile
        label="Publication failed"
        :value="formatGovernNumber(coverage.totals.unavailable)"
        helper="Never estimated or back-filled"
        tone="critical"
      />
    </div>

    <GovernCaveat tone="info" title="What these percentages can carry">
      They count fixture rows per producer, not tenants or requests. A projection row is deliberately counted as
      uncertified, so a high "re-provable" figure never becomes a completeness claim.
    </GovernCaveat>

    <div class="console-panel p-3">
      <div class="flex h-2 w-full overflow-hidden rounded-full bg-raised" role="img" aria-label="Evidence tier composition">
        <span
          v-for="tier in EVIDENCE_TIERS"
          :key="tier"
          :style="{ width: `${totalPercent(tier)}%` }"
          :class="TIER_BAR_CLASS[tier]"
        />
      </div>
      <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[0.6875rem] text-fg-3">
        <span v-for="tier in EVIDENCE_TIERS" :key="tier" class="inline-flex items-center gap-1.5" :title="EVIDENCE_TIER_MEANING[tier]">
          <span class="size-2 rounded-[2px]" :class="TIER_BAR_CLASS[tier]" aria-hidden="true" />
          {{ EVIDENCE_TIER_LABELS[tier] }}
          <span class="font-mono tabular-nums text-fg-2">{{ formatGovernNumber(coverage.totals[tier]) }}</span>
          <span class="font-mono tabular-nums">{{ formatGovernPercent(totalPercent(tier), 1) }}</span>
        </span>
      </div>
    </div>

    <div class="ix-scroll overflow-x-auto rounded-lg border border-line-subtle">
      <table class="ix-agent-table table-fixed" style="min-width: 1000px" aria-label="Evidence coverage by producer">
        <thead>
          <tr>
            <th scope="col" style="width: 230px">Producer</th>
            <th scope="col" style="width: 140px">Capture mode</th>
            <th scope="col" style="width: 90px" class="text-right">Records</th>
            <th scope="col" style="width: 200px">Tier mix</th>
            <th scope="col" style="width: 110px" class="text-right">Re-provable</th>
            <th scope="col" style="width: 120px">Last evidence row</th>
            <th scope="col" style="width: 110px">Oldest unresolved</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.id"
            tabindex="0"
            class="cursor-pointer"
            :data-selected="selected === row.id ? 'true' : undefined"
            @click="toggle(row)"
            @keydown.enter.prevent="toggle(row)"
            @keydown.space.prevent="toggle(row)"
          >
            <td>
              <p class="truncate text-xs font-medium text-fg-1" :title="row.label">{{ row.label }}</p>
              <p class="mt-0.5 truncate font-mono text-[0.625rem] leading-4 text-fg-3" :title="row.service">{{ row.service }}</p>
            </td>
            <td class="text-xs text-fg-2">{{ CAPTURE_MODE_LABELS[row.captureMode] }}</td>
            <td class="text-right font-mono text-xs text-fg-2 tabular-nums">{{ formatGovernNumber(evidenceProducerTotal(row)) }}</td>
            <td>
              <span class="flex h-2 w-full overflow-hidden rounded-full bg-surface-2" role="img" :aria-label="tierMixLabel(row)">
                <span
                  v-for="tier in EVIDENCE_TIERS"
                  :key="tier"
                  :style="{ width: `${evidenceTierPercent(row, tier)}%` }"
                  :class="TIER_BAR_CLASS[tier]"
                />
              </span>
              <span class="mt-1 flex flex-wrap gap-x-2 font-mono text-[0.625rem] leading-4 text-fg-3 tabular-nums">
                <span v-for="tier in EVIDENCE_TIERS" :key="tier" :class="TIER_TEXT_CLASS[tier]" :title="EVIDENCE_TIER_MEANING[tier]">
                  {{ formatGovernNumber(row.counts[tier]) }}
                </span>
              </span>
            </td>
            <td class="text-right font-mono text-xs text-fg-1 tabular-nums">
              {{ row.counts.evidence === 0 ? "None" : formatGovernPercent(evidenceTierPercent(row, "evidence")) }}
            </td>
            <td>
              <span v-if="row.lastEvidenceAt" class="font-mono text-[0.6875rem] whitespace-nowrap text-fg-2" :title="formatGovernStamp(row.lastEvidenceAt)">
                {{ formatGovernRelative(row.lastEvidenceAt) }}
              </span>
              <span v-else class="text-xs text-fg-3">Not recorded</span>
            </td>
            <td>
              <span v-if="row.oldestPendingAt" class="font-mono text-[0.6875rem] whitespace-nowrap text-warn" :title="formatGovernStamp(row.oldestPendingAt)">
                {{ formatGovernRelative(row.oldestPendingAt) }}
              </span>
              <span v-else class="text-xs text-fg-3">Nothing open</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p class="text-[0.6875rem] leading-4 text-fg-3">
      Select a producer to keep it while you read the tombstone and chain tabs. Counts are fixtures for
      {{ formatGovernNumber(coverage.records) }} records in this window.
    </p>
  </div>
</template>
