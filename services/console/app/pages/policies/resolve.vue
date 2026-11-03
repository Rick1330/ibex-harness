<script setup lang="ts">
import { ref, watch } from "vue"
import { useRoute } from "vue-router"
import PolicyResolveView from "@/components/console/policy/resolve/PolicyResolveView.vue"
import { parsePolicyResolveQuery, serializePolicyResolveQuery, type PolicyResolveState } from "@/lib/govern-query"
import { safePolicyReturn } from "@/lib/return-to"

const route = useRoute()
const state = ref<PolicyResolveState>(parsePolicyResolveQuery(route.query))
const returnTo = ref(safePolicyReturn(route.query.return))

watch(
  () => route.query,
  () => {
    if (route.path !== "/policies/resolve") return
    state.value = parsePolicyResolveQuery(route.query)
    returnTo.value = safePolicyReturn(route.query.return)
  },
)

function update(next: PolicyResolveState): void {
  state.value = next
  if (!import.meta.client) return
  const query = Object.fromEntries(serializePolicyResolveQuery(next))
  const preserved = returnTo.value !== "/policies" ? { return: returnTo.value } : {}
  void navigateTo({ query: { ...query, ...preserved } }, { replace: true })
}

useHead({ title: "Resolve a run · Policies · IBEX Console" })
</script>

<template>
  <PolicyResolveView :state="state" :return-to="returnTo" @update="update" />
</template>
