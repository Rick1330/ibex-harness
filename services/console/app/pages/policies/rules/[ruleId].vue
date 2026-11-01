<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useRoute } from "vue-router"
import PolicyRuleDetailView from "@/components/console/policy/detail/PolicyRuleDetailView.vue"
import {
  POLICY_CURRENT_SNAPSHOT,
  policyCurrentSnapshot,
  policyRuleAt,
  policyRuleById,
  policySnapshotById,
} from "@/lib/policy-preview"
import {
  parsePolicyRuleDetailQueryV2,
  serializePolicyRuleDetailQueryV2,
  type PolicyRuleDetailStateV2,
} from "@/lib/govern-query"
import { safePolicyReturn } from "@/lib/return-to"

const route = useRoute()
const ruleId = computed(() => String(route.params.ruleId ?? ""))
const rule = computed(() => policyRuleById(ruleId.value))
const state = ref<PolicyRuleDetailStateV2>(parsePolicyRuleDetailQueryV2(route.query))
const snapshot = computed(() => policySnapshotById(state.value.snapshot) ?? policyCurrentSnapshot())
const snapshotRevision = computed(() => (rule.value ? policyRuleAt(rule.value.id, snapshot.value.id) : null))
const revision = computed(() => {
  if (!rule.value) return null
  if (state.value.rev !== null) {
    const selected = rule.value.revisions.find((entry) => entry.revision === state.value.rev)
    if (selected) return selected
  }
  return snapshotRevision.value
})
const returnTo = computed(() => safePolicyReturn(route.query.return))

watch(
  () => route.query,
  () => {
    if (!route.path.startsWith("/policies/rules/")) return
    state.value = parsePolicyRuleDetailQueryV2(route.query)
  },
)

function update(next: PolicyRuleDetailStateV2): void {
  state.value = next
  if (!import.meta.client) return
  const query = Object.fromEntries(serializePolicyRuleDetailQueryV2(next))
  const preserved = typeof route.query.return === "string" ? { return: route.query.return } : {}
  void navigateTo({ query: { ...query, ...preserved } }, { replace: true })
}

useHead(() => ({
  title: `${rule.value?.label ?? "Rule not found"} · Policies · IBEX Console`,
}))
</script>

<template>
  <PolicyRuleDetailView
    v-if="rule && revision"
    :rule="rule"
    :revision="revision"
    :snapshot="snapshot"
    :return-to="returnTo"
    :state="state"
    @update="update"
  />
  <section
    v-else-if="rule"
    class="mx-auto w-full max-w-[90rem] rounded-lg border border-line-subtle bg-surface-1 p-6"
    aria-labelledby="rule-snapshot-missing"
  >
    <NuxtLink :to="returnTo" class="text-xs text-fg-3 hover:text-fg-1">← Back to policies</NuxtLink>
    <h1 id="rule-snapshot-missing" class="mt-4 text-lg font-semibold text-fg-1">Rule is not in this snapshot</h1>
    <p class="mt-1 max-w-[70ch] text-sm text-fg-3">
      {{ rule.label }} has no published revision in {{ snapshot.id }}. Snapshots are immutable, so the rule is shown
      where it was published instead of being synthesized here.
    </p>
    <NuxtLink
      :to="`/policies/rules/${encodeURIComponent(rule.id)}?snapshot=${POLICY_CURRENT_SNAPSHOT}`"
      class="ix-button-secondary mt-4 inline-flex h-8 items-center text-xs"
    >
      Open in {{ POLICY_CURRENT_SNAPSHOT }}
    </NuxtLink>
  </section>
  <section
    v-else
    class="mx-auto w-full max-w-[90rem] rounded-lg border border-line-subtle bg-surface-1 p-6"
    aria-labelledby="rule-not-found"
  >
    <NuxtLink :to="returnTo" class="text-xs text-fg-3 hover:text-fg-1">← Back to policies</NuxtLink>
    <h1 id="rule-not-found" class="mt-4 text-lg font-semibold text-fg-1">Rule not found</h1>
    <p class="mt-1 text-sm text-fg-3">This rule ID is not in the preview policy set. Live policy lookups are not connected.</p>
  </section>
</template>
