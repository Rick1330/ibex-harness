<script setup lang="ts">
import { computed } from "vue"
import { Download } from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import GovernTabBar from "@/components/console/govern/primitives/GovernTabBar.vue"
import IxVerdict from "@/components/console/IxVerdict.vue"
import { useOperatorDirective } from "@/composables/useOperatorData"
import { formatGovernNumber, formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"
import { isOperatorAuthError, operatorFailureDetail } from "@/lib/operator-error"
import {
  formatBytes,
  injectionModeLabel,
  mostUsedVersion,
  sessionsOffPointer,
  versionByNumber,
} from "@/lib/directive-summary"
import {
  serializeLiveDirectiveDetailQuery,
  type LiveDirectiveDetailQuery,
} from "~~/shared/operator/directive-query"
import type { DirectiveUsageRange } from "~~/shared/operator/contracts"

const props = defineProps<{
  directiveId: string
  state: LiveDirectiveDetailQuery
  returnTo: string
}>()
const emit = defineEmits<{ update: [state: LiveDirectiveDetailQuery] }>()

const tab = defineModel<"versions" | "usage" | "diff" | "promotion" | "audit">("tab", {
  default: "versions",
})

const directiveState = useOperatorDirective(
  () => props.directiveId,
  () => serializeLiveDirectiveDetailQuery(props.state),
)
const detail = computed(() => directiveState.data.value ?? null)
const error = computed(() => directiveState.error.value)
const authIssue = computed(() => isOperatorAuthError(error.value))
const notFound = computed(() => (error.value as { statusCode?: number } | null)?.statusCode === 404)
const failureDetail = computed(() =>
  error.value && !notFound.value && !authIssue.value ? operatorFailureDetail(error.value) : null,
)
const loading = computed(
  () => !detail.value && !error.value && directiveState.status.value === "pending",
)

const rangeOptions: { value: DirectiveUsageRange; label: string }[] = [
  { value: "24h", label: "Last 24 hours" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
]

const tabs = [
  { id: "versions", label: "Versions" },
  { id: "usage", label: "Usage" },
  { id: "diff", label: "Diff" },
  { id: "promotion", label: "Promotion" },
  { id: "audit", label: "Audit" },
] as const

const tabBadges = computed<Record<string, string>>(() => {
  const badges: Record<string, string> = {}
  if (!detail.value) return badges
  badges.versions = formatGovernNumber(detail.value.version_count)
  badges.usage = formatGovernNumber(detail.value.usage.reduce((sum, row) => sum + row.sessions, 0))
  return badges
})

const clock = computed(() => detail.value?.observed_at ?? null)

const liveVersion = computed(() =>
  detail.value ? versionByNumber(detail.value, detail.value.active_version_num) : null,
)
const busiest = computed(() => (detail.value ? mostUsedVersion(detail.value) : null))
const offPointer = computed(() => (detail.value ? sessionsOffPointer(detail.value) : 0))
// Exact sessions in the window; the table may list only the busiest versions.
const servedSessions = computed(() => detail.value?.usage_total_sessions ?? 0)

const verdict = computed(() => {
  if (loading.value) return "Reading the directive and its versions…"
  if (authIssue.value) return "The operator session cannot read this organization"
  if (notFound.value) return "This directive does not exist in this organization"
  if (error.value) return "Directive unavailable"
  const data = detail.value
  if (!data) return "Directive unavailable"
  if (!data.is_active) return "This directive is inactive: new sessions resolve to no version"
  if (data.active_version_num === null) {
    return data.active_version_missing
      ? "The live pointer names a version this read cannot see"
      : "No version has been published for this directive"
  }
  return `New sessions resolve to v${data.active_version_num}`
})

const coverage = computed(() => {
  const data = detail.value
  if (!data) return "No data shown"
  return `${formatGovernNumber(data.version_count)} versions · ${formatGovernNumber(servedSessions.value)} sessions in range`
})

function update(patch: Partial<LiveDirectiveDetailQuery>): void {
  emit("update", { ...props.state, ...patch })
}

function copyLink(): void {
  if (!import.meta.client || !detail.value) return
  void navigator.clipboard.writeText(`${window.location.origin}/directives/${detail.value.id}`)
}
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">
    <ConsolePageHeader
      :title="detail ? detail.agent_name : 'Directive'"
      definition="The version a new session resolves to, every version behind it, and which of them actually served traffic."
      state="live"
      :verdict="verdict"
      contract="operator.directives.versions.v1"
      scope="Organization"
      :range="`Usage: ${rangeOptions.find((option) => option.value === state.range)?.label ?? state.range}`"
      :coverage="coverage"
      :observed="detail?.observed_at ?? null"
      caveat="Version identity only: the instruction text is not in this contract, so no diff or promotion history is shown."
    >
      <template #actions>
        <GovernFilterSelect
          label="Usage range"
          :model-value="state.range"
          :options="rangeOptions"
          default-value="7d"
          @update:model-value="update({ range: $event as DirectiveUsageRange })"
        />
        <GovernLockedAction label="Export" :icon="Download" />
      </template>
    </ConsolePageHeader>

    <div v-if="detail" class="flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[0.6875rem] text-fg-3">
      <NuxtLink :to="returnTo" class="hover:text-fg-1">← Back to directives</NuxtLink>
      <GovernCopyId :id="detail.agent_slug" label="Agent" truncate />
      <span>{{ injectionModeLabel(detail.injection_mode) }}</span>
      <button type="button" class="hover:text-fg-1" @click="copyLink">Copy link</button>
    </div>

    <GovernTabBar
      :tabs="[...tabs]"
      :model-value="tab"
      aria-label="Directive views"
      :badges="tabBadges"
      @update:model-value="tab = $event as typeof tab"
    />

    <!-- Tabs without a contract explain themselves regardless of the read state. -->
    <GovernEmptyState
      v-if="tab === 'diff'"
      title="Version diff is not part of this contract"
      reason="A diff needs both versions' instruction text, and this contract carries identity only: number, digest prefix, and size."
      next-step="A content and diff read model needs its own contract behind the redacted-read permission."
      action-label="Back to versions"
      @action="tab = 'versions'"
    />
    <GovernEmptyState
      v-else-if="tab === 'promotion'"
      title="Promotion history is not part of this contract"
      reason="The console is read-only: promoting or rolling back a version needs a write path with step-up, CSRF, and an audit record. No such events exist to show."
      next-step="Use the version timeline to see which version the pointer names today."
      action-label="Back to versions"
      @action="tab = 'versions'"
    />
    <GovernEmptyState
      v-else-if="tab === 'audit'"
      title="Directive audit is not part of this contract"
      reason="The operator action ledger records console actions. No directive action has ever been recorded because the console has no directive write path."
      next-step="Open the audit log once a write contract exists; until then there is nothing to list."
      action-label="Open the audit log"
      @action="navigateTo('/audit')"
    />
    <IxVerdict
      v-else-if="loading"
      tone="unknown"
      eyebrow="Live operator read"
      title="Reading the directive"
      body="Asking the operator API for the version timeline."
    />
    <IxVerdict
      v-else-if="authIssue"
      tone="unavailable"
      eyebrow="Operator session"
      title="The operator session cannot read this organization"
      body="Sign in again with an account that holds metadata-read permission."
    />
    <IxVerdict
      v-else-if="notFound"
      tone="unknown"
      eyebrow="Live operator read"
      title="Directive not found"
      body="The identifier resolved to nothing inside your organization. Another organization's directive is reported the same way."
    />
    <IxVerdict
      v-else-if="error"
      tone="unknown"
      eyebrow="Live operator read"
      title="Directive unavailable"
      :body="failureDetail ?? 'The upstream read failed. No values are inferred.'"
    />

    <template v-else-if="detail">
      <template v-if="tab === 'versions'">
        <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4">
          <GovernStatTile
            label="Live version"
            :value="detail.active_version_num === null ? 'None' : `v${detail.active_version_num}`"
            :helper="detail.is_active ? 'What a new session resolves to' : 'Directive inactive'"
            :tone="detail.active_version_num === null ? 'warning' : 'success'"
          />
          <GovernStatTile
            label="Versions"
            :value="formatGovernNumber(detail.version_count)"
            helper="Append-only; numbers are never reused"
          />
          <GovernStatTile
            label="Size of the live version"
            :value="liveVersion ? formatBytes(liveVersion.content_bytes) : 'Not published'"
            helper="Stored instruction bytes, not the text"
          />
          <GovernStatTile
            label="Last version"
            :value="detail.last_version_at ? formatGovernRelative(detail.last_version_at, clock) : 'None'"
            :helper="detail.last_version_at ? formatGovernStamp(detail.last_version_at) : 'No version published'"
          />
        </div>

        <GovernCaveat v-if="detail.versions_truncated" tone="info" title="The timeline is partial">
          This directive has {{ formatGovernNumber(detail.version_count) }} versions. The newest 200 are listed, plus the
          version the pointer names when it is older than that window, so a rollback stays visible.
        </GovernCaveat>

        <GovernCaveat v-if="detail.active_version_missing" tone="warning" title="The pointer names an unseen version">
          The directive points at a version this read did not return. Treat the live version as unknown rather than
          assuming the newest one is live.
        </GovernCaveat>

        <div class="ix-scroll overflow-x-auto rounded-lg border border-line-subtle">
          <table class="ix-agent-table table-fixed" style="min-width: 780px" aria-label="Directive versions">
            <thead>
              <tr>
                <th scope="col" style="width: 90px">Version</th>
                <th scope="col" style="width: 140px">Digest</th>
                <th scope="col" style="width: 100px" class="text-right">Size</th>
                <th scope="col" style="width: 150px">Created</th>
                <th scope="col" style="width: 120px">Status</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="version in detail.versions" :key="version.version_num">
                <td class="font-mono tabular-nums text-xs text-fg-1">v{{ version.version_num }}</td>
                <td class="font-mono text-[0.6875rem] text-fg-2" :title="'Identity prefix, not a verifier'">
                  {{ version.content_digest }}
                </td>
                <td class="text-right font-mono tabular-nums text-xs text-fg-2">
                  {{ formatBytes(version.content_bytes) }}
                </td>
                <td>
                  <span class="text-xs text-fg-2" :title="formatGovernStamp(version.created_at)">
                    {{ formatGovernRelative(version.created_at, clock) }}
                  </span>
                </td>
                <td>
                  <span v-if="version.is_live" class="text-xs font-medium text-ok">Live</span>
                  <span v-else class="text-xs text-fg-3">Superseded</span>
                </td>
              </tr>
              <tr v-if="!detail.versions.length">
                <td colspan="5" class="px-3 py-6 text-center text-xs text-fg-3">
                  No version has been published for this directive.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <template v-else-if="tab === 'usage'">
        <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4">
          <GovernStatTile
            label="Sessions in range"
            :value="formatGovernNumber(servedSessions)"
            helper="Sessions that recorded a directive version"
          />
          <GovernStatTile
            label="Busiest version"
            :value="busiest ? `v${busiest.version_num}` : 'None'"
            :helper="busiest ? `${formatGovernNumber(busiest.sessions)} sessions` : 'No usage in range'"
          />
          <GovernStatTile
            label="Off the live pointer"
            :value="formatGovernNumber(offPointer)"
            helper="Ran before the pointer moved; not stale data"
          />
          <GovernStatTile
            label="Window starts"
            :value="formatGovernRelative(detail.usage_window_start, clock)"
            :helper="formatGovernStamp(detail.usage_window_start)"
          />
        </div>

        <div class="ix-scroll overflow-x-auto rounded-lg border border-line-subtle">
          <table class="ix-agent-table table-fixed" style="min-width: 620px" aria-label="Directive usage by version">
            <thead>
              <tr>
                <th scope="col" style="width: 110px">Version</th>
                <th scope="col" style="width: 120px" class="text-right">Sessions</th>
                <th scope="col" style="width: 150px">Last session</th>
                <th scope="col" style="width: 120px">Pointer</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in detail.usage" :key="row.version_num">
                <td class="font-mono tabular-nums text-xs text-fg-1">v{{ row.version_num }}</td>
                <td class="text-right font-mono tabular-nums text-xs text-fg-2">
                  {{ formatGovernNumber(row.sessions) }}
                </td>
                <td>
                  <span
                    v-if="row.last_session_at"
                    class="text-xs text-fg-2"
                    :title="formatGovernStamp(row.last_session_at)"
                  >
                    {{ formatGovernRelative(row.last_session_at, clock) }}
                  </span>
                  <span v-else class="text-xs text-fg-3">Not recorded</span>
                </td>
                <td>
                  <span v-if="row.version_num === detail.active_version_num" class="text-xs text-ok">Current</span>
                  <span v-else class="text-xs text-fg-3">Earlier</span>
                </td>
              </tr>
              <tr v-if="!detail.usage.length">
                <td colspan="4" class="px-3 py-6 text-center text-xs text-fg-3">
                  No session in this window resolved to a version of this directive.
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <GovernCaveat v-if="detail.usage_truncated" tone="info" title="The table lists the busiest versions">
          This directive has more versions in use than fit here. The session total above is exact; the table shows the
          {{ detail.usage.length }} versions with the most sessions in the window.
        </GovernCaveat>

        <GovernCaveat tone="info" title="Usage comes from the session record">
          Each session stores the version it resolved when it started, so an older version can still serve traffic after
          a rollback. That is the expected shape, not drift.
        </GovernCaveat>
      </template>

    </template>
  </div>
</template>
