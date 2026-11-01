<script setup lang="ts">
import { ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import IncidentListView from "@/components/console/incident/IncidentListView.vue"
import {
  parseIncidentQuery,
  serializeIncidentQuery,
  type IncidentListState,
} from "@/lib/incident-preview"

const route = useRoute()
const router = useRouter()
const state = ref<IncidentListState>(parseIncidentQuery(route.query))

useHead({ title: "Incidents · IBEX Console" })

function serialized(value: IncidentListState): string {
  return serializeIncidentQuery(value).toString()
}

watch(
  state,
  (next) => {
    if (!import.meta.client) return
    if (serialized(next) === serialized(parseIncidentQuery(route.query))) return
    void router.replace({ query: Object.fromEntries(serializeIncidentQuery(next)) }).catch(() => undefined)
  },
  { deep: true },
)

watch(
  () => route.query,
  () => {
    if (route.path !== "/incidents") return
    const parsed = parseIncidentQuery(route.query)
    if (serialized(parsed) !== serialized(state.value)) state.value = parsed
  },
)
</script>

<template>
  <IncidentListView :state="state" @update="state = $event" />
</template>
