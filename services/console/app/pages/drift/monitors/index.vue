<script setup lang="ts">
import { ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import DriftMonitorsView from "@/components/console/drift/monitor/DriftMonitorsView.vue"
import {
  parseDriftMonitorListQuery,
  serializeDriftMonitorListQuery,
  type DriftMonitorListState,
} from "@/lib/govern-query"

const route = useRoute()
const router = useRouter()
const state = ref<DriftMonitorListState>(parseDriftMonitorListQuery(route.query))

useHead({ title: "Drift monitors · IBEX Console" })

function serialized(value: DriftMonitorListState): string {
  return serializeDriftMonitorListQuery(value).toString()
}

watch(
  state,
  (next) => {
    if (!import.meta.client) return
    if (serialized(next) === serialized(parseDriftMonitorListQuery(route.query))) return
    void router.replace({ query: Object.fromEntries(serializeDriftMonitorListQuery(next)) }).catch(() => undefined)
  },
  { deep: true },
)

watch(
  () => route.query,
  () => {
    if (route.path !== "/drift/monitors") return
    const parsed = parseDriftMonitorListQuery(route.query)
    if (serialized(parsed) === serialized(state.value)) return
    state.value = parsed
  },
)
</script>

<template>
  <DriftMonitorsView :state="state" @update="state = $event" />
</template>
