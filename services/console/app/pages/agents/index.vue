<script setup lang="ts">
import { onMounted, ref, watch } from "vue"
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router"
import AgentListView from "@/components/console/agent/list/AgentListView.vue"
import {
  defaultLiveAgentQuery,
  parseLiveAgentQuery,
  serializeLiveAgentUrlQuery,
  type LiveAgentQuery,
} from "~~/shared/operator/agent-query"

const SNAPSHOT_KEY = "ibex:agent-list:return"

type Snapshot = {
  path: string
  scrollY: number
}

const route = useRoute()
const router = useRouter()
const state = ref<LiveAgentQuery>(stateFromQuery(route.query))
const returnTo = ref(route.fullPath)

useHead({ title: "Agents · IBEX Console" })

function stateFromQuery(query: Record<string, unknown>): LiveAgentQuery {
  try {
    return parseLiveAgentQuery(query)
  } catch {
    return defaultLiveAgentQuery()
  }
}

function serialized(value: LiveAgentQuery): string {
  return serializeLiveAgentUrlQuery(value).toString()
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
      .replace({ query: Object.fromEntries(serializeLiveAgentUrlQuery(next)) })
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
    if (route.path !== "/agents") return
    const parsed = stateFromQuery(route.query)
    if (serialized(parsed) === serialized(state.value)) {
      returnTo.value = route.fullPath
      return
    }
    state.value = parsed
    returnTo.value = route.fullPath
  },
)

function saveSnapshot(): void {
  if (!import.meta.client) return
  try {
    const snapshot: Snapshot = { path: route.fullPath, scrollY: window.scrollY }
    sessionStorage.setItem(SNAPSHOT_KEY, JSON.stringify(snapshot))
  } catch {
    /* session storage is optional */
  }
}

function restoreSnapshot(): void {
  if (!import.meta.client) return
  let stored: Snapshot | null = null
  try {
    const raw = sessionStorage.getItem(SNAPSHOT_KEY)
    sessionStorage.removeItem(SNAPSHOT_KEY)
    stored = raw ? (JSON.parse(raw) as Snapshot) : null
  } catch {
    stored = null
  }
  if (!stored || stored.path !== route.fullPath) return
  requestAnimationFrame(() => window.scrollTo({ top: stored!.scrollY, behavior: "instant" }))
}

onBeforeRouteLeave(() => {
  saveSnapshot()
  return true
})

onMounted(() => {
  restoreSnapshot()
})
</script>

<template>
  <AgentListView :state="state" :return-to="returnTo" @update="state = $event" />
</template>
