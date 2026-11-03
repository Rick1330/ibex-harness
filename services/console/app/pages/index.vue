<script setup lang="ts">
import { ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import OverviewView from "@/components/console/overview/OverviewView.vue"
import { parseOverviewQuery, serializeOverviewQuery, type OverviewState } from "@/lib/govern-query"

const route = useRoute()
const router = useRouter()
const state = ref<OverviewState>(parseOverviewQuery(route.query))

useHead({ title: "Overview · IBEX Console" })

function serialized(value: OverviewState): string {
  return serializeOverviewQuery(value).toString()
}

watch(
  state,
  (next) => {
    if (!import.meta.client) return
    if (serialized(next) === serialized(parseOverviewQuery(route.query))) return
    void router.replace({ query: Object.fromEntries(serializeOverviewQuery(next)) }).catch(() => undefined)
  },
  { deep: true },
)

watch(
  () => route.query,
  () => {
    if (route.path !== "/") return
    const parsed = parseOverviewQuery(route.query)
    if (serialized(parsed) === serialized(state.value)) return
    state.value = parsed
  },
)
</script>

<template>
  <OverviewView :state="state" @update="state = $event" />
</template>
