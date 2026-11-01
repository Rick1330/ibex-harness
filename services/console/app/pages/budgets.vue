<script setup lang="ts">
import { ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import BudgetView from "@/components/console/budget/BudgetView.vue"
import { parseBudgetQuery, serializeBudgetQuery, type BudgetListState } from "@/lib/govern-query"

const route = useRoute()
const router = useRouter()
const state = ref<BudgetListState>(parseBudgetQuery(route.query))

useHead({ title: "Budgets · IBEX Console" })

function serialized(value: BudgetListState): string {
  return serializeBudgetQuery(value).toString()
}

watch(
  state,
  (next) => {
    if (!import.meta.client) return
    if (serialized(next) === serialized(parseBudgetQuery(route.query))) return
    void router.replace({ query: Object.fromEntries(serializeBudgetQuery(next)) }).catch(() => undefined)
  },
  { deep: true },
)

watch(
  () => route.query,
  () => {
    if (route.path !== "/budgets") return
    const parsed = parseBudgetQuery(route.query)
    if (serialized(parsed) === serialized(state.value)) return
    state.value = parsed
  },
)
</script>

<template>
  <BudgetView :state="state" @update="state = $event" />
</template>
