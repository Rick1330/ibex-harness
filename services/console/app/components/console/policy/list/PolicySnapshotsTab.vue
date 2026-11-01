<script setup lang="ts">
import { computed } from "vue"
import { ChevronRight, GitCompareArrows, Info, Radio } from "@lucide/vue"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernHashTag from "@/components/console/govern/primitives/GovernHashTag.vue"
import { formatGovernShortDate, formatGovernStamp } from "@/lib/govern-format"
import {
  policyRulesForSnapshot,
  policySnapshotChangeSummary,
  policySnapshotState,
  policySnapshots,
} from "@/lib/policy-preview"
import { policyCompareHref, policySnapshotHref } from "@/lib/govern-query"

const rows = computed(() =>
  policySnapshots.map((snapshot) => ({
    snapshot,
    state: policySnapshotState(snapshot.id),
    changes: policySnapshotChangeSummary(snapshot.id),
    rules: policyRulesForSnapshot(snapshot.id).length,
    compare: snapshot.previousId
      ? policyCompareHref({ from: snapshot.previousId, to: snapshot.id, hideUnchanged: false })
      : null,
  })),
)

function changeLabel(entry: (typeof rows.value)[number]): string {
  if (entry.changes.metadataOnly) return "Metadata only"
  if (entry.changes.changed === 0) return "No rule changes"
  return `${entry.changes.changed} ${entry.changes.changed === 1 ? "rule" : "rules"} changed`
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
      <div class="ix-scroll overflow-x-auto">
        <table class="ix-agent-table" aria-label="Snapshot history">
          <thead>
            <tr>
              <th scope="col" class="min-w-56">Snapshot</th>
              <th scope="col" class="w-24">Effective</th>
              <th scope="col" class="hidden w-32 min-[1200px]:table-cell">Published by</th>
              <th scope="col" class="w-40">Change</th>
              <th scope="col" class="w-16 text-right">Rules</th>
              <th scope="col" class="hidden w-40 min-[1360px]:table-cell">Digest</th>
              <th scope="col" class="w-24"><span class="sr-only">Compare</span></th>
              <th scope="col" class="w-10"><span class="sr-only">Open</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entry in rows" :key="entry.snapshot.id">
              <td>
                <div class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                  <span
                    class="inline-flex h-5 shrink-0 items-center gap-1 rounded-full border px-1.5 text-[0.625rem] leading-none font-medium"
                    :class="entry.state === 'live' ? 'border-transparent bg-transparent text-ok' : 'border-line bg-raised text-fg-3'"
                  >
                    <Radio :size="9" :stroke-width="2.2" aria-hidden="true" />
                    {{ entry.state === "live" ? "Live" : "Superseded" }}
                  </span>
                  <NuxtLink
                    :to="policySnapshotHref(entry.snapshot.id)"
                    class="font-mono text-[0.8125rem] font-medium text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline"
                  >
                    {{ entry.snapshot.id }}
                  </NuxtLink>
                  <GovernCopyId :id="entry.snapshot.id" label="Snapshot ID" icon-only />
                </div>
                <p class="mt-1 max-w-md truncate text-xs text-fg-2" :title="entry.snapshot.message">{{ entry.snapshot.message }}</p>
              </td>
              <td>
                <span class="text-xs text-fg-2" :title="formatGovernStamp(entry.snapshot.effectiveFrom)">
                  {{ formatGovernShortDate(entry.snapshot.effectiveFrom) }}
                </span>
              </td>
              <td class="hidden min-[1200px]:table-cell">
                <span class="text-xs text-fg-2">{{ entry.snapshot.publishedBy }}</span>
              </td>
              <td>
                <span class="inline-flex flex-wrap items-center gap-1.5 text-xs" :class="entry.changes.metadataOnly ? 'text-fg-3' : 'text-fg-2'">
                  {{ changeLabel(entry) }}
                  <Tooltip v-if="entry.changes.metadataOnly" :delay-duration="120">
                    <TooltipTrigger as-child>
                      <span tabindex="0" class="inline-flex text-fg-3" aria-label="Metadata-only change">
                        <Info :size="12" :stroke-width="1.9" aria-hidden="true" />
                      </span>
                    </TooltipTrigger>
                    <TooltipContent side="top" class="!max-w-72 !text-xs">{{ entry.changes.reason }}</TooltipContent>
                  </Tooltip>
                </span>
                <span v-if="entry.changes.names.length" class="mt-0.5 block max-w-40 truncate text-[0.625rem] text-fg-3" :title="entry.changes.names.join(', ')">
                  {{ entry.changes.names.join(", ") }}
                </span>
              </td>
              <td class="text-right">
                <span class="font-mono text-xs text-fg-2 tabular-nums">{{ entry.rules }}</span>
              </td>
              <td class="hidden min-[1360px]:table-cell">
                <GovernHashTag :hash="entry.snapshot.digest" label="snapshot digest" />
              </td>
              <td>
                <NuxtLink
                  v-if="entry.compare"
                  :to="entry.compare"
                  class="inline-flex h-7 items-center gap-1 rounded px-1.5 text-[0.6875rem] font-medium text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                  :aria-label="`Compare ${entry.snapshot.previousId} with ${entry.snapshot.id}`"
                >
                  <GitCompareArrows :size="12" :stroke-width="1.9" aria-hidden="true" />
                  Compare
                </NuxtLink>
                <span v-else class="text-[0.6875rem] text-fg-3">First snapshot</span>
              </td>
              <td>
                <NuxtLink
                  :to="policySnapshotHref(entry.snapshot.id)"
                  class="inline-flex size-6 items-center justify-center rounded text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                  :aria-label="`Open snapshot ${entry.snapshot.id}`"
                >
                  <ChevronRight :size="14" :stroke-width="1.9" aria-hidden="true" />
                </NuxtLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <footer class="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line-subtle bg-canvas/30 px-4 py-1.5 text-[0.6875rem] leading-4 text-fg-3">
        <span>Snapshots are immutable. A metadata-only snapshot keeps the same rule bytes and records a new release note.</span>
        <span class="ml-auto font-mono">{{ rows.length }} snapshots</span>
      </footer>
    </div>
  </div>
</template>
