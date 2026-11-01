<script setup lang="ts">
import { computed, ref } from "vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import { formatGovernNumber } from "@/lib/govern-format"
import type { EvidenceRedactionRow } from "@/lib/evidence-preview"

const props = defineProps<{ rows: EvidenceRedactionRow[] }>()

const selectedId = ref<string | null>(props.rows[0]?.id ?? null)
const selected = computed(() => props.rows.find((row) => row.id === selectedId.value) ?? props.rows[0] ?? null)

const totals = computed(() =>
  props.rows.reduce(
    (sum, row) => ({
      metadata: sum.metadata + row.metadata,
      redacted: sum.redacted + row.redacted,
      withheld: sum.withheld + row.withheld,
    }),
    { metadata: 0, redacted: 0, withheld: 0 },
  ),
)

function select(row: EvidenceRedactionRow): void {
  selectedId.value = row.id
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <GovernStatTile label="Metadata rows" :value="formatGovernNumber(totals.metadata)" helper="Readable without content" />
      <GovernStatTile
        label="Redacted rows"
        :value="formatGovernNumber(totals.redacted)"
        helper="Fields removed before storage"
        tone="warning"
      />
      <GovernStatTile
        label="Withheld rows"
        :value="formatGovernNumber(totals.withheld)"
        helper="Identity or fence missing"
        tone="critical"
      />
      <GovernStatTile
        label="Proof versions"
        :value="String(new Set(rows.map((row) => row.proofVersion)).size)"
        helper="Versioned sanitizers in use"
      />
    </div>

    <GovernCaveat tone="info" title="Redaction is a classification, not a repair">
      A redacted row is persisted as non-projectable evidence. The relay rejects it rather than inferring safety, so a
      missing field is never filled from a later read.
    </GovernCaveat>

    <div class="ix-scroll overflow-x-auto rounded-lg border border-line-subtle">
      <table class="ix-agent-table table-fixed" style="min-width: 900px" aria-label="Redaction by pipeline">
        <thead>
          <tr>
            <th scope="col" style="width: 250px">Pipeline</th>
            <th scope="col" style="width: 230px">Proof version</th>
            <th scope="col" style="width: 90px" class="text-right">Metadata</th>
            <th scope="col" style="width: 90px" class="text-right">Redacted</th>
            <th scope="col" style="width: 90px" class="text-right">Withheld</th>
            <th scope="col" style="width: 130px">Removed fields</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.id"
            tabindex="0"
            class="cursor-pointer"
            :data-selected="selectedId === row.id ? 'true' : undefined"
            @click="select(row)"
            @keydown.enter.prevent="select(row)"
            @keydown.space.prevent="select(row)"
          >
            <td>
              <p class="truncate text-xs font-medium text-fg-1" :title="row.label">{{ row.label }}</p>
              <p class="mt-0.5 truncate font-mono text-[0.625rem] leading-4 text-fg-3" :title="row.service">{{ row.service }}</p>
            </td>
            <td class="truncate font-mono text-[0.6875rem] text-fg-2" :title="row.proofVersion">{{ row.proofVersion }}</td>
            <td class="text-right font-mono text-xs text-fg-2 tabular-nums">{{ formatGovernNumber(row.metadata) }}</td>
            <td class="text-right font-mono text-xs text-warn tabular-nums">{{ formatGovernNumber(row.redacted) }}</td>
            <td class="text-right font-mono text-xs" :class="row.withheld ? 'text-crit' : 'text-fg-3'" tabular-nums>
              {{ formatGovernNumber(row.withheld) }}
            </td>
            <td class="font-mono text-xs text-fg-2 tabular-nums">{{ row.droppedFields.length }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <section v-if="selected" class="rounded-lg border border-line-subtle bg-surface p-4" aria-labelledby="redaction-detail">
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="redaction-detail" class="text-sm leading-5 font-semibold text-fg-1">{{ selected.label }}</h3>
        <span class="font-mono text-[0.6875rem] text-fg-3">{{ selected.proofVersion }}</span>
      </div>
      <p class="mt-1.5 max-w-3xl text-xs leading-4 text-fg-3 text-pretty">{{ selected.note }}</p>

      <div class="ix-scroll mt-4 overflow-x-auto rounded-lg border border-line-subtle" tabindex="0" role="region" aria-label="Removed fields">
        <table class="w-full min-w-[34rem] text-left text-xs" aria-label="Removed fields">
          <thead class="border-b border-line-subtle text-[0.625rem] tracking-[0.08em] text-fg-3 uppercase">
            <tr>
              <th scope="col" class="px-3 py-2 font-medium">Removed field</th>
              <th scope="col" class="px-3 py-2 font-medium">Why it is not metadata</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-line-subtle">
            <tr v-for="field in selected.droppedFields" :key="field.field">
              <td class="px-3 py-2 font-mono text-[0.6875rem] text-fg-1">{{ field.field }}</td>
              <td class="px-3 py-2 text-fg-2">{{ field.reason }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
