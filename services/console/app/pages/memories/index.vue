<script setup lang="ts">
import { ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import MemoryListView from "@/components/console/memory/live/LiveMemoryListView.vue"
import {
  defaultLiveMemoryQuery,
  parseLiveMemoryQuery,
  serializeLiveMemoryQuery,
  type LiveMemoryQuery,
} from "~~/shared/operator/memory-query"

const route = useRoute()
const router = useRouter()
const state = ref<LiveMemoryQuery>(stateFromQuery(route.query))
const returnTo = ref(route.fullPath)

useHead({ title: "Memories · IBEX Console" })

function stateFromQuery(query: Record<string, unknown>): LiveMemoryQuery {
  try {
    return parseLiveMemoryQuery(query)
  } catch {
    return defaultLiveMemoryQuery()
  }
}

function serialized(value: LiveMemoryQuery): string {
  return serializeLiveMemoryQuery(value).toString()
}

watch(
  state,
  (next) => {
    if (!import.meta.client) return
    if (serialized(next) === serialized(stateFromQuery(route.query))) {
      returnTo.value = route.fullPath
      return
    }
    void router
      .replace({ query: Object.fromEntries(serializeLiveMemoryQuery(next)) })
      .then(() => {
        returnTo.value = route.fullPath
      })
      .catch(() => undefined)
  },
  { deep: true },
)

watch(
  () => route.query,
  () => {
    if (route.path !== "/memories") return
    const parsed = stateFromQuery(route.query)
    if (serialized(parsed) === serialized(state.value)) {
      returnTo.value = route.fullPath
      return
    }
    state.value = parsed
    returnTo.value = route.fullPath
  },
)
</script>

<template>
  <MemoryListView :state="state" :return-to="returnTo" @update="state = $event" />
</template>
