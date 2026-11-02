<script setup lang="ts">
import { ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import LiveSessionListView from "@/components/console/session/live/LiveSessionListView.vue"
import {
  defaultLiveSessionQuery,
  parseLiveSessionQuery,
  serializeLiveSessionQuery,
  type LiveSessionQuery,
} from "~~/shared/operator/session-query"

const route = useRoute()
const router = useRouter()
const state = ref<LiveSessionQuery>(stateFromQuery(route.query))
const returnTo = ref(route.fullPath)

useHead({ title: "Sessions · IBEX Console" })

function stateFromQuery(query: Record<string, unknown>): LiveSessionQuery {
  try {
    return parseLiveSessionQuery(query)
  } catch {
    return defaultLiveSessionQuery()
  }
}

function serialized(value: LiveSessionQuery): string {
  return serializeLiveSessionQuery(value).toString()
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
      .replace({ query: Object.fromEntries(serializeLiveSessionQuery(next)) })
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
    if (route.path !== "/sessions") return
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
  <LiveSessionListView :state="state" :return-to="returnTo" @update="state = $event" />
</template>
