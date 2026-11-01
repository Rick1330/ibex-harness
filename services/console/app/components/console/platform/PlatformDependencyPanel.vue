<script setup lang="ts">
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernPendingData from "@/components/console/govern/primitives/GovernPendingData.vue"
import GovernSeverityChip from "@/components/console/govern/primitives/GovernSeverityChip.vue"
import { PLATFORM_CONTRACT, PLATFORM_PENDING, type PlatformDependencyRow } from "@/lib/platform-view"

const props = defineProps<{
  rows: PlatformDependencyRow[]
  /** The snapshot resolved but came back with no checks. */
  resolved: boolean
  loading: boolean
  authIssue: boolean
}>()

const emit = defineEmits<{ retry: [] }>()

const STATUS_CLASS = {
  ok: "text-ok",
  degraded: "text-warn",
  unavailable: "text-crit",
} as const
</script>

<template>
  <section class="flex min-w-0 flex-col gap-3" aria-label="Dependency ledger">
    <div v-if="props.authIssue" class="rounded-lg border border-line-subtle bg-surface p-1">
      <GovernEmptyState
        title="Platform health needs an operator session that allows platform reads"
        reason="The snapshot was refused, so no dependency is shown. An unverified session is never replaced with a sample report."
        next-step="Re-read once the session carries the platform read permission."
        action-label="Re-read"
        @action="emit('retry')"
      />
    </div>

    <GovernPendingData
      v-else-if="props.loading && !props.resolved"
      title="Platform snapshot"
      :contract="PLATFORM_CONTRACT"
      description="Reading the dependency, ingestion, recovery and deployment fields in one request."
    />

    <div
      v-else-if="!props.rows.length"
      class="rounded-lg border border-line-subtle bg-surface p-1"
    >
      <GovernEmptyState
        :title="props.resolved ? 'The snapshot reported no dependency checks' : 'No dependency snapshot was read'"
        :reason="
          props.resolved
            ? 'dependency_health came back empty. Every check the platform normally runs is unknown to this page, which is not the same as every check passing.'
            : 'operator.platform.health.v1 did not resolve for this session, so there is no status to list.'
        "
        :next-step="props.resolved ? 'The ingestion, recovery and deployment tabs report the same absence field by field.' : null"
        :action-label="props.resolved ? null : 'Re-read'"
        @action="emit('retry')"
      />
    </div>

    <template v-else>
      <div class="ix-scroll min-w-0 overflow-x-auto rounded-lg border border-line-subtle">
        <table class="ix-agent-table table-fixed" style="min-width: 820px" aria-label="Dependency status as reported">
          <thead>
            <tr>
              <th scope="col" style="width: 220px">Dependency</th>
              <th scope="col" style="width: 130px">Status</th>
              <th scope="col" style="width: 120px">Severity</th>
              <th scope="col" style="width: 350px">What the platform reported</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in props.rows" :key="row.code" class="align-top">
              <td>
                <p class="truncate text-xs font-medium text-fg-1" :title="row.label">{{ row.label }}</p>
                <p class="truncate font-mono text-[0.625rem] leading-4 text-fg-3" :title="row.code">{{ row.code }}</p>
              </td>
              <td>
                <span class="text-xs" :class="STATUS_CLASS[row.status]">{{ row.statusLabel }}</span>
              </td>
              <td>
                <GovernSeverityChip v-if="row.severity" :severity="row.severity" />
                <span v-else class="text-[0.6875rem] text-fg-3">No finding</span>
              </td>
              <td class="text-[0.6875rem] leading-4 text-fg-3">{{ row.meaning }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <GovernCaveat tone="info" title="Status words, not a legend">
        The status column repeats the platform's own value as text, so severity is never carried by colour alone.
        A row with no severity chip is a dependency reporting ok, which is an observation inside this snapshot and
        not a statement that the dependency was reachable a minute later.
      </GovernCaveat>

      <div class="grid gap-2 sm:grid-cols-2">
        <GovernPendingData
          v-for="slot in PLATFORM_PENDING"
          :key="slot.title"
          :title="slot.title"
          :contract="slot.contract"
          :description="slot.description"
        />
      </div>
    </template>
  </section>
</template>
