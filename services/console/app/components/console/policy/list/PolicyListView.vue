<script setup lang="ts">
import { computed, ref } from "vue"
import { Copy } from "@lucide/vue"
import GovernShortcutsDialog from "@/components/console/govern/primitives/GovernShortcutsDialog.vue"
import GovernTabBar from "@/components/console/govern/primitives/GovernTabBar.vue"
import PolicyChangesTab from "./PolicyChangesTab.vue"
import PolicyDecisionsTab from "./PolicyDecisionsTab.vue"
import PolicyListHeader from "./PolicyListHeader.vue"
import PolicyRulesTab from "./PolicyRulesTab.vue"
import PolicySnapshotBar from "./PolicySnapshotBar.vue"
import PolicySnapshotsTab from "./PolicySnapshotsTab.vue"
import {
  POLICY_TAB_LABELS,
  policyCompareHref,
  policyListHrefV2,
  POLICY_COMPARE_DEFAULT,
  type PolicyListStateV2,
  type PolicyTab,
} from "@/lib/govern-query"
import {
  policyChangeFeed,
  policyDecisionsSince,
  policyRulesForSnapshot,
  policySnapshotById,
  policySnapshots,
} from "@/lib/policy-preview"
import { GOVERN_NOW } from "@/lib/govern-format"
import { useGovernShortcuts } from "@/composables/useGovernShortcuts"

const props = defineProps<{
  state: PolicyListStateV2
  returnTo: string
}>()

const emit = defineEmits<{ update: [state: PolicyListStateV2] }>()

function update(patch: Partial<PolicyListStateV2>): void {
  emit("update", { ...props.state, ...patch })
}

const snapshot = computed(() => policySnapshotById(props.state.snapshot) ?? policySnapshots[0]!)
const rules = computed(() => policyRulesForSnapshot(snapshot.value.id))

const decisionWindowMs = computed(() => (props.state.range === "30d" ? 30 : 7) * 86_400_000)
const decisionCount = computed(
  () =>
    policyDecisionsSince(new Date(GOVERN_NOW - decisionWindowMs.value).toISOString(), snapshot.value.id).length,
)
const changeCount = policyChangeFeed().length

const tabs = computed(() => [
  { id: "rules", label: `${POLICY_TAB_LABELS.rules} (${rules.value.length})` },
  { id: "decisions", label: `Decisions (${props.state.range})` },
  { id: "snapshots", label: `${POLICY_TAB_LABELS.snapshots} (${policySnapshots.length})` },
  { id: "changes", label: POLICY_TAB_LABELS.changes },
])

const badges = computed<Record<string, string>>(() => ({
  decisions: String(decisionCount.value),
  changes: String(changeCount),
}))

function selectTab(id: string): void {
  update({ tab: id as PolicyTab })
}

const header = ref<InstanceType<typeof PolicyListHeader> | null>(null)
const rulesTab = ref<InstanceType<typeof PolicyRulesTab> | null>(null)
const decisionsTab = ref<InstanceType<typeof PolicyDecisionsTab> | null>(null)

function focusSearch(): void {
  if (props.state.tab === "rules") rulesTab.value?.focusSearch()
  else if (props.state.tab === "decisions") decisionsTab.value?.focusSearch()
}

function copyCurrentLink(): void {
  if (!import.meta.client) return
  void navigator.clipboard.writeText(`${window.location.origin}${policyListHrefV2(props.state)}`)
}

const { helpOpen } = useGovernShortcuts({
  onSearch: focusSearch,
  keys: {
    c: () => void navigateTo(policyCompareHref({ ...POLICY_COMPARE_DEFAULT, to: snapshot.value.id })),
    y: copyCurrentLink,
  },
})

const shortcutGroups = [
  {
    title: "Move",
    rows: [
      { keys: "j / k", label: "Next / previous row" },
      { keys: "Enter", label: "Open the selected row" },
      { keys: "Space", label: "Open the 480px peek" },
      { keys: "/", label: "Focus search" },
      { keys: "Esc", label: "Clear selection or search" },
    ],
  },
  {
    title: "This page",
    rows: [
      { keys: "c", label: "Compare snapshots" },
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
    <PolicyListHeader ref="header" :snapshot="snapshot" :rule-count="rules.length" />

    <PolicySnapshotBar
      :snapshot="snapshot"
      :snapshots="policySnapshots"
      @update:snapshot="update({ snapshot: $event })"
    />

    <GovernTabBar
      :tabs="tabs"
      :model-value="state.tab"
      :badges="badges"
      aria-label="Policy views"
      @update:model-value="selectTab"
    />

    <div class="min-w-0">
      <PolicyRulesTab
        v-if="state.tab === 'rules'"
        ref="rulesTab"
        :state="state"
        :snapshot-id="snapshot.id"
        :return-to="returnTo"
        @update="update"
      />
      <PolicyDecisionsTab
        v-else-if="state.tab === 'decisions'"
        ref="decisionsTab"
        :state="state"
        :snapshot-id="snapshot.id"
        @update="update"
      />
      <PolicySnapshotsTab v-else-if="state.tab === 'snapshots'" />
      <PolicyChangesTab v-else />
    </div>

    <p class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.6875rem] leading-4 text-fg-3">
      <span class="inline-flex items-center gap-1"><Copy :size="10" :stroke-width="1.8" aria-hidden="true" /> Press c to compare, y to copy this view, ? for shortcuts.</span>
      <span class="ml-auto font-mono">READ-ONLY</span>
    </p>

    <GovernShortcutsDialog v-model:open="helpOpen" :groups="shortcutGroups" />
  </div>
</template>
