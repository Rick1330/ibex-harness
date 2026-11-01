<script setup lang="ts">
import { ref, watch } from "vue"
import { useRoute } from "vue-router"
import PolicyCompareView from "@/components/console/policy/compare/PolicyCompareView.vue"
import { parsePolicyCompareQuery, serializePolicyCompareQuery, type PolicyCompareState } from "@/lib/govern-query"
import { safePolicyReturn } from "@/lib/return-to"

const route = useRoute()
const state = ref<PolicyCompareState>(parsePolicyCompareQuery(route.query))
const returnTo = ref(safePolicyReturn(route.query.return))

watch(
  () => route.query,
  () => {
    if (route.path !== "/policies/compare") return
    state.value = parsePolicyCompareQuery(route.query)
    returnTo.value = safePolicyReturn(route.query.return)
  },
)

function update(next: PolicyCompareState): void {
  state.value = next
  if (!import.meta.client) return
  const query = Object.fromEntries(serializePolicyCompareQuery(next))
  const preserved = returnTo.value !== "/policies" ? { return: returnTo.value } : {}
  void navigateTo({ query: { ...query, ...preserved } }, { replace: true })
}

useHead({ title: "Compare snapshots · Policies · IBEX Console" })
</script>

<template>
  <PolicyCompareView :state="state" :return-to="returnTo" @update="update" />
</template>
