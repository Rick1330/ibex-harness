<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import {
  ChevronLeft,
  ChevronRight,
  Clock,
  Copy,
  Ellipsis,
  ExternalLink,
  FileJson,
  GitCompareArrows,
  Pencil,
  Radio,
} from "@lucide/vue"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import GovernAboutPopover from "@/components/console/govern/primitives/GovernAboutPopover.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernDataSourceChip from "@/components/console/govern/primitives/GovernDataSourceChip.vue"
import GovernEffectTag from "@/components/console/govern/primitives/GovernEffectTag.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import GovernModeTag from "@/components/console/govern/primitives/GovernModeTag.vue"
import GovernTabBar from "@/components/console/govern/primitives/GovernTabBar.vue"
import PolicyRuleOverviewTab from "./tabs/PolicyRuleOverviewTab.vue"
import PolicyRuleFiresTab from "./tabs/PolicyRuleFiresTab.vue"
import PolicyRuleHistoryTab from "./tabs/PolicyRuleHistoryTab.vue"
import PolicyRuleScopeTab from "./tabs/PolicyRuleScopeTab.vue"
import { formatGovernShortDate } from "@/lib/govern-format"
import {
  POLICY_CURRENT_SNAPSHOT,
  POLICY_RULE_TABS,
  policyRuleRuns,
  policyRules,
  type PolicyRule,
  type PolicyRuleRevision,
  type PolicyRuleTab,
  type PolicySnapshot,
} from "@/lib/policy-preview"
import {
  policyRuleDetailHref,
  policySnapshotHref,
  type PolicyRuleDetailStateV2,
} from "@/lib/govern-query"

const props = defineProps<{
  rule: PolicyRule
  revision: PolicyRuleRevision
  snapshot: PolicySnapshot
  returnTo: string
  state: PolicyRuleDetailStateV2
}>()

const emit = defineEmits<{ update: [state: PolicyRuleDetailStateV2] }>()

function update(patch: Partial<PolicyRuleDetailStateV2>): void {
  emit("update", { ...props.state, ...patch })
}

function selectTab(tab: PolicyRuleTab): void {
  update({ tab })
}

const latestRevision = computed(() => props.rule.revisions[0]!)
const isCurrentSnapshot = computed(() => props.snapshot.id === POLICY_CURRENT_SNAPSHOT)
const isOldRevision = computed(() => props.revision.revision !== latestRevision.value.revision)
const fires = computed(() => policyRuleRuns(props.rule.id))

const tabs = computed(() => [
  { id: "overview", label: "Overview" },
  { id: "fires", label: "Fires" },
  { id: "history", label: "History" },
  { id: "scope", label: "Where it applies" },
])

const badges = computed<Record<string, string>>(() => ({
  fires: String(fires.value.length),
  history: String(props.rule.revisions.length),
}))

const currentIndex = computed(() => policyRules.findIndex((rule) => rule.id === props.rule.id))
const prevRule = computed(() => (currentIndex.value > 0 ? policyRules[currentIndex.value - 1]! : null))
const nextRule = computed(() =>
  currentIndex.value >= 0 && currentIndex.value < policyRules.length - 1 ? policyRules[currentIndex.value + 1]! : null,
)

function detailHref(ruleId: string, snapshotId = props.snapshot.id): string {
  const href = policyRuleDetailHref(ruleId, { tab: "overview", snapshot: snapshotId, rev: null })
  return `${href}?return=${encodeURIComponent(props.returnTo)}`
}

function goRule(ruleId: string): void {
  void navigateTo(detailHref(ruleId))
}

function showLiveRevision(): void {
  update({ snapshot: POLICY_CURRENT_SNAPSHOT, rev: null })
}

function showRevision(revisionNumber: number): void {
  update({ rev: revisionNumber })
}

const snapshotHref = computed(() => policySnapshotHref(props.snapshot.id))

const about = ref<InstanceType<typeof GovernAboutPopover> | null>(null)

function copyText(value: string): void {
  if (import.meta.client) void navigator.clipboard.writeText(value)
}

function currentOrigin(): string {
  return import.meta.client ? window.location.origin : ""
}

function onGlobalKeydown(event: KeyboardEvent): void {
  if (event.metaKey || event.ctrlKey || event.altKey) return
  if (event.target instanceof HTMLElement && event.target.closest("input, textarea, select, [contenteditable]")) return
  if (event.key === "[") {
    if (prevRule.value) {
      event.preventDefault()
      goRule(prevRule.value.id)
    }
  } else if (event.key === "]") {
    if (nextRule.value) {
      event.preventDefault()
      goRule(nextRule.value.id)
    }
  } else if (/^[1-4]$/.test(event.key)) {
    const target = POLICY_RULE_TABS[Number(event.key) - 1]
    if (target) {
      event.preventDefault()
      selectTab(target.id)
    }
  }
}

onMounted(() => window.addEventListener("keydown", onGlobalKeydown))
onBeforeUnmount(() => window.removeEventListener("keydown", onGlobalKeydown))
</script>

<template>
  <div class="mx-auto flex w-full max-w-[90rem] min-w-0 flex-1 flex-col pb-2">
    <header class="min-w-0">
      <div class="flex items-center justify-between gap-3">
        <NuxtLink
          :to="returnTo"
          class="inline-flex items-center gap-1.5 rounded text-xs text-fg-3 transition-colors hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        >
          <ChevronLeft :size="13" :stroke-width="1.9" aria-hidden="true" />
          Back to policies
        </NuxtLink>
        <div class="flex items-center gap-0.5">
          <button
            type="button"
            class="inline-flex size-7 items-center justify-center rounded-md text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 disabled:pointer-events-none disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            :disabled="!prevRule"
            :aria-label="prevRule ? `Previous rule: ${prevRule.label}` : 'No previous rule'"
            @click="prevRule && goRule(prevRule.id)"
          >
            <ChevronLeft :size="15" :stroke-width="1.9" aria-hidden="true" />
          </button>
          <button
            type="button"
            class="inline-flex size-7 items-center justify-center rounded-md text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 disabled:pointer-events-none disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            :disabled="!nextRule"
            :aria-label="nextRule ? `Next rule: ${nextRule.label}` : 'No next rule'"
            @click="nextRule && goRule(nextRule.id)"
          >
            <ChevronRight :size="15" :stroke-width="1.9" aria-hidden="true" />
          </button>
        </div>
      </div>

      <div class="mt-3.5 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
            <h1 class="ix-page-title text-fg-1 text-pretty">{{ rule.label }}</h1>
            <GovernEffectTag :effect="revision.effect" />
            <GovernModeTag :mode="revision.mode" />
            <span
              v-if="isOldRevision"
              class="inline-flex h-5.5 items-center gap-1 rounded-full border border-warn/30 bg-warn-tint px-2 text-xs leading-none font-medium text-warn"
            >
              <Clock :size="10" :stroke-width="2" aria-hidden="true" />
              @{{ revision.revision }} · superseded
            </span>
          </div>
          <div class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
            <span class="font-mono text-sm text-fg-2">{{ rule.id }}@{{ revision.revision }}</span>
            <GovernCopyId :id="`${rule.id}@${revision.revision}`" label="Rule revision" icon-only />
            <span class="text-fg-off" aria-hidden="true">·</span>
            <span class="text-xs text-fg-3">{{ rule.area }} · {{ rule.scope }}</span>
          </div>
          <p class="mt-1.5 max-w-[76ch] text-sm leading-5 text-fg-2">{{ revision.summary }}</p>
          <p class="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs leading-4 text-fg-3">
            <span>Revision <span class="font-mono text-fg-2">@{{ revision.revision }}</span> by {{ revision.changedBy }}, effective {{ formatGovernShortDate(revision.effectiveFrom) }}</span>
            <span aria-hidden="true">·</span>
            <NuxtLink :to="snapshotHref" class="inline-flex items-center gap-1 text-fg-3 underline decoration-line-strong underline-offset-3 hover:text-fg-1">
              <Radio :size="11" :stroke-width="1.9" aria-hidden="true" />
              <span class="font-mono">{{ snapshot.id }}</span>
            </NuxtLink>
          </p>
        </div>

        <div class="flex shrink-0 flex-wrap items-center gap-2">
          <GovernDataSourceChip :live="false" @open="about?.open()" />
          <GovernAboutPopover
            ref="about"
            :verdict="`Rule ${rule.id} is shown as published in ${snapshot.id}. Runtime composition and rule ordering are owned by the policy engine, not this page.`"
            contract="operator.policies.snapshots.v1"
            :scope="rule.scope"
            :range="`@${rule.revisions.at(-1)!.revision} → @${latestRevision.revision}`"
            coverage="Preview fixtures · no policy read model connected"
            phase="D5 · Phase B2"
            claim="No enforcement, audit, or billing claim."
            :notes="[
              { lead: 'Rules belong to snapshots.', body: 'A rule revision is immutable inside the snapshot that published it. Editing a rule means publishing a new snapshot, never rewriting history.' },
              { lead: 'Advisory rules still record.', body: 'An advisory rule logs its decision as a warning and the run continues. The effect label describes intent; the mode says whether it is applied.' },
              { lead: 'Provenance is joined, not assumed.', body: 'Linked runs join the decision log. Partial provenance means the join is incomplete, not that the rule was skipped.' },
            ]"
          />
          <GovernLockedAction label="Edit rule" :icon="Pencil" variant="primary" />
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <button
                type="button"
                class="inline-flex size-8 items-center justify-center rounded-md border border-line bg-surface-1 text-fg-2 transition-colors hover:border-line-strong hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                aria-label="More rule actions"
              >
                <Ellipsis :size="15" :stroke-width="1.9" aria-hidden="true" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" class="!w-64">
              <DropdownMenuLabel class="text-xs text-fg-3">Rule</DropdownMenuLabel>
              <DropdownMenuItem class="!text-xs" @select="copyText(rule.id)">
                <Copy :size="13" :stroke-width="1.9" aria-hidden="true" /> Copy ID
              </DropdownMenuItem>
              <DropdownMenuItem class="!text-xs" @select="copyText(`${currentOrigin()}${detailHref(rule.id, POLICY_CURRENT_SNAPSHOT)}`)">
                <ExternalLink :size="13" :stroke-width="1.9" aria-hidden="true" /> Copy link
              </DropdownMenuItem>
              <DropdownMenuItem class="!text-xs" @select="selectTab('history')">
                <GitCompareArrows :size="13" :stroke-width="1.9" aria-hidden="true" /> Compare revisions
              </DropdownMenuItem>
              <DropdownMenuItem class="!text-xs" @select="copyText(JSON.stringify(rule, null, 2))">
                <FileJson :size="13" :stroke-width="1.9" aria-hidden="true" /> Export JSON
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem class="!text-xs" disabled title="Read-only console. Requires a privileged write contract.">
                <Pencil :size="13" :stroke-width="1.9" aria-hidden="true" /> Publish revision
                <span class="ml-auto text-[0.625rem] text-fg-3">new snapshot</span>
              </DropdownMenuItem>
              <p class="border-t border-line-subtle px-2 py-2 text-[0.625rem] leading-3.5 text-fg-3">
                Read-only console. Requires a privileged write contract.
              </p>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>

    <div
      v-if="!isCurrentSnapshot"
      class="mt-4 flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-line-subtle bg-warn-tint/40 px-4 py-2 text-xs leading-5 text-fg-2"
    >
      <Clock :size="13" :stroke-width="1.9" class="shrink-0 text-warn" aria-hidden="true" />
      <p class="min-w-0 flex-1">
        This rule is shown as published in the superseded snapshot <span class="font-mono">{{ snapshot.id }}</span>. The runtime is governed by
        <span class="font-mono">{{ POLICY_CURRENT_SNAPSHOT }}</span>.
      </p>
      <button type="button" class="shrink-0 font-medium underline decoration-line-strong underline-offset-3 hover:text-fg-1" @click="showLiveRevision">
        Show live revision
      </button>
    </div>

    <div
      v-else-if="isOldRevision"
      class="mt-4 flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-line-subtle bg-warn-tint/40 px-4 py-2 text-xs leading-5 text-fg-2"
    >
      <Clock :size="13" :stroke-width="1.9" class="shrink-0 text-warn" aria-hidden="true" />
      <p class="min-w-0 flex-1">
        You are viewing revision <span class="font-mono">@{{ revision.revision }}</span> as it read before
        <span class="font-mono">@{{ latestRevision.revision }}</span>. The runtime uses
        <span class="font-mono">@{{ latestRevision.revision }}</span>.
      </p>
      <button type="button" class="shrink-0 font-medium underline decoration-line-strong underline-offset-3 hover:text-fg-1" @click="showRevision(latestRevision.revision)">
        Show live revision
      </button>
    </div>

    <div class="mt-5">
      <GovernTabBar
        :tabs="tabs"
        :model-value="state.tab"
        :badges="badges"
        aria-label="Policy rule views"
        @update:model-value="selectTab($event as PolicyRuleTab)"
      />
    </div>

    <div class="mt-5 min-w-0">
      <Transition name="govern-panel" mode="out-in">
        <div :key="state.tab" role="tabpanel" :aria-labelledby="`govern-tab-${state.tab}`" tabindex="0" class="min-w-0">
          <PolicyRuleOverviewTab
            v-if="state.tab === 'overview'"
            :rule="rule"
            :revision="revision"
            :snapshot="snapshot"
            @revision="showRevision"
            @tab="selectTab"
          />
          <PolicyRuleFiresTab v-else-if="state.tab === 'fires'" :rule="rule" :return-to="returnTo" />
          <PolicyRuleHistoryTab v-else-if="state.tab === 'history'" :rule="rule" :revision="revision" @revision="showRevision" />
          <PolicyRuleScopeTab v-else :rule="rule" :snapshot="snapshot" />
        </div>
      </Transition>
    </div>

    <p class="mt-8 text-[0.6875rem] leading-4 text-fg-3">
      Read-only. Press 1–4 for tabs, [ and ] for the previous/next rule.
    </p>
  </div>
</template>

<style scoped>
.govern-panel-enter-active {
  transition: opacity 150ms ease, transform 150ms ease;
}
.govern-panel-leave-active {
  transition: opacity 100ms ease;
}
.govern-panel-enter-from {
  opacity: 0;
  transform: translateY(4px);
}
.govern-panel-leave-to {
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .govern-panel-enter-active,
  .govern-panel-leave-active {
    transition: none;
  }
}
</style>
