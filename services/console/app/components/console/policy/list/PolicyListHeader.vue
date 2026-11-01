<script setup lang="ts">
import { computed, ref } from "vue"
import { GitCompareArrows, Plus, Workflow } from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import type { PolicySnapshot } from "@/lib/policy-preview"
import { policyCompareHref, POLICY_COMPARE_DEFAULT } from "@/lib/govern-query"

const props = defineProps<{
  snapshot: PolicySnapshot
  ruleCount: number
}>()

const about = ref<InstanceType<typeof ConsolePageHeader> | null>(null)
const compareHref = computed(() => policyCompareHref({ ...POLICY_COMPARE_DEFAULT, to: props.snapshot.id }))

const notes = [
  {
    lead: "Rules are published as snapshots.",
    body: "A snapshot is immutable. Editing a rule publishes a new snapshot and keeps the previous one for time travel.",
  },
  {
    lead: "Fired counts are joined from decisions.",
    body: "A rule without decision data shows Not reported, never zero. Partial provenance lowers the count rather than hiding it.",
  },
  {
    lead: "Impact is replayed, not simulated here.",
    body: "Impact numbers come from replaying recorded decisions server-side. This console never evaluates a policy client-side.",
  },
]

function openAbout(): void {
  about.value?.openAbout()
}

defineExpose({ openAbout })
</script>

<template>
  <ConsolePageHeader
    ref="about"
    title="Policies"
    definition="The rules the runtime checks before an agent acts, and how often each one fired."
    state="illustrative"
    verdict="Every value on this page is an illustrative fixture. The runtime does not serve policy data to this console yet."
    contract="operator.policies.snapshots.v1 [NEEDS-BACKEND]"
    scope="org_demo_42 · workspace ws_42"
    range="Four illustrative snapshots, 11–27 Oct 2026"
    coverage="Preview fixtures · no policy read model connected"
    :notes="notes"
  >
    <template #actions>
      <NuxtLink :to="compareHref" class="ix-button-secondary">
        <GitCompareArrows :size="13" :stroke-width="1.8" aria-hidden="true" />
        Compare
      </NuxtLink>
      <NuxtLink to="/policies/resolve" class="ix-button-secondary">
        <Workflow :size="13" :stroke-width="1.8" aria-hidden="true" />
        Resolve a run
      </NuxtLink>
      <GovernLockedAction label="New snapshot" :icon="Plus" variant="primary" />
    </template>
  </ConsolePageHeader>
</template>
