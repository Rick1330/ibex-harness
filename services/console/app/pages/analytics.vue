<script setup lang="ts">
import { ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import AnalyticsView from "@/components/console/analytics/AnalyticsView.vue"
import { parseAnalyticsQuery, serializeAnalyticsQuery, type AnalyticsListState } from "@/lib/govern-query"

const route = useRoute()
const router = useRouter()
const state = ref<AnalyticsListState>(parseAnalyticsQuery(route.query))

useHead({ title: "Analytics · IBEX Console" })

function serialized(value: AnalyticsListState): string {
  return serializeAnalyticsQuery(value).toString()
}

watch(
  state,
  (next) => {
    if (!import.meta.client) return
    if (serialized(next) === serialized(parseAnalyticsQuery(route.query))) return
    void router.replace({ query: Object.fromEntries(serializeAnalyticsQuery(next)) }).catch(() => undefined)
  },
  { deep: true },
)

watch(
  () => route.query,
  () => {
    if (route.path !== "/analytics") return
    const parsed = parseAnalyticsQuery(route.query)
    if (serialized(parsed) === serialized(state.value)) return
    state.value = parsed
  },
)
</script>

<template>
  <AnalyticsView :state="state" @update="state = $event" />
</template>
