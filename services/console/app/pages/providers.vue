<script setup lang="ts">
import { ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import ProviderListView from "@/components/console/provider/ProviderListView.vue"
import {
  parseProviderQuery,
  serializeProviderQuery,
  type ProviderListState,
} from "@/lib/provider-preview"

const route = useRoute()
const router = useRouter()
const state = ref<ProviderListState>(parseProviderQuery(route.query))

useHead({ title: "Providers · IBEX Console" })

function serialized(value: ProviderListState): string {
  return serializeProviderQuery(value).toString()
}

watch(
  state,
  (next) => {
    if (!import.meta.client) return
    if (serialized(next) === serialized(parseProviderQuery(route.query))) return
    void router.replace({ query: Object.fromEntries(serializeProviderQuery(next)) }).catch(() => undefined)
  },
  { deep: true },
)

watch(
  () => route.query,
  () => {
    if (route.path !== "/providers") return
    const parsed = parseProviderQuery(route.query)
    if (serialized(parsed) !== serialized(state.value)) state.value = parsed
  },
)
</script>

<template>
  <ProviderListView :state="state" @update="state = $event" />
</template>
