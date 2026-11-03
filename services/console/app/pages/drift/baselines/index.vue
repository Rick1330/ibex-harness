<script setup lang="ts">
import { ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import DriftBaselinesView from "@/components/console/drift/baseline/DriftBaselinesView.vue"
import {
  parseDriftBaselineListQuery,
  serializeDriftBaselineListQuery,
  type DriftBaselineListState,
} from "@/lib/govern-query"

const route = useRoute()
const router = useRouter()
const state = ref<DriftBaselineListState>(parseDriftBaselineListQuery(route.query))

useHead({ title: "Drift baselines · IBEX Console" })

function serialized(value: DriftBaselineListState): string {
  return serializeDriftBaselineListQuery(value).toString()
}

watch(
  state,
  (next) => {
    if (!import.meta.client) return
    if (serialized(next) === serialized(parseDriftBaselineListQuery(route.query))) return
    void router.replace({ query: Object.fromEntries(serializeDriftBaselineListQuery(next)) }).catch(() => undefined)
  },
  { deep: true },
)

watch(
  () => route.query,
  () => {
    if (route.path !== "/drift/baselines") return
    const parsed = parseDriftBaselineListQuery(route.query)
    if (serialized(parsed) === serialized(state.value)) return
    state.value = parsed
  },
)
</script>

<template>
  <DriftBaselinesView :state="state" @update="state = $event" />
</template>
