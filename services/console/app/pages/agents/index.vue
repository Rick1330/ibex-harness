<script setup lang="ts">
import { onMounted, ref, watch } from "vue"
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router"
import AgentListView from "@/components/console/agent/list/AgentListView.vue"
import {
  parseAgentListQuery,
  serializeAgentListQuery,
  type AgentListState,
} from "@/lib/agent-list-query"

const SNAPSHOT_KEY = "ibex:agent-list:return"

type Snapshot = {
  path: string
  scrollY: number
}

const route = useRoute()
const router = useRouter()
const state = ref<AgentListState>(parseAgentListQuery(route.query))
const returnTo = ref(route.fullPath)

useHead({ title: "Agents · IBEX Console" })

function serialized(value: AgentListState): string {
  return serializeAgentListQuery(value).toString()
}

function queryFrom(value: AgentListState): Record<string, string> {
  return Object.fromEntries(serializeAgentListQuery(value))
}

function isSearchOnly(next: AgentListState): boolean {
  const current = parseAgentListQuery(route.query)
  const withoutSearch = (value: AgentListState) => serialized({ ...value, search: "" })
  return withoutSearch(next) === withoutSearch(current) && next.search !== current.search
}

function update(next: AgentListState): void {
  state.value = next
}

watch(
  state,
  (next) => {
    if (!import.meta.client) return
    if (serialized(next) === serialized(parseAgentListQuery(route.query))) {
      returnTo.value = route.fullPath
      return
    }
    void router
      .replace({ query: queryFrom(next) })
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
    const parsed = parseAgentListQuery(route.query)
    if (serialized(parsed) === serialized(state.value)) {
      returnTo.value = route.fullPath
      return
    }
    // Search is owned by the debounced input; ignore echo writes from it.
    if (!isSearchOnly(parsed)) state.value = parsed
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
  <AgentListView :state="state" :return-to="returnTo" @update="update" />
</template>
