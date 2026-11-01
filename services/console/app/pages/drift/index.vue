<script setup lang="ts">
import { ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import DriftListView from "@/components/console/drift/list/DriftListView.vue"
import { parseDriftListQuery, serializeDriftListQuery, type DriftListState } from "@/lib/govern-query"

const route = useRoute()
const router = useRouter()
const state = ref<DriftListState>(parseDriftListQuery(route.query))

useHead({ title: "Drift · IBEX Console" })

function serialized(value: DriftListState): string {
  return serializeDriftListQuery(value).toString()
}

function queryFrom(value: DriftListState): Record<string, string> {
  return Object.fromEntries(serializeDriftListQuery(value))
}

watch(
  state,
  (next) => {
    if (!import.meta.client) return
    if (serialized(next) === serialized(parseDriftListQuery(route.query))) return
    void router.replace({ query: queryFrom(next) }).catch(() => undefined)
  },
  { deep: true },
)

watch(
  () => route.query,
  () => {
    if (route.path !== "/drift") return
    const parsed = parseDriftListQuery(route.query)
    if (serialized(parsed) === serialized(state.value)) return
    state.value = parsed
  },
)
</script>

<template>
  <DriftListView :state="state" @update="state = $event" />
</template>
