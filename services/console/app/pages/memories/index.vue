<script setup lang="ts">
import { onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import MemoryListView from "@/components/console/memory/live/LiveMemoryListView.vue"
import {
  parseLiveMemoryQuery,
  parseLiveMemoryQueryLenient,
  serializeLiveMemoryQuery,
  type LiveMemoryQuery,
} from "~~/shared/operator/memory-query"

const route = useRoute()
const router = useRouter()
const state = ref<LiveMemoryQuery>(stateFromQuery(route.query))
const returnTo = ref(route.fullPath)

useHead({ title: "Memories · IBEX Console" })

function strictStateFromQuery(query: Record<string, unknown>): LiveMemoryQuery | null {
  try {
    return parseLiveMemoryQuery(query)
  } catch {
    return null
  }
}

// A stale or hand-edited link must not widen the read: keep the filters that
// parse, and let `normalizeUrl` drop the rest from the address bar so it always
// describes the list on screen.
function stateFromQuery(query: Record<string, unknown>): LiveMemoryQuery {
  return strictStateFromQuery(query) ?? parseLiveMemoryQueryLenient(query)
}

function serialized(value: LiveMemoryQuery): string {
  return serializeLiveMemoryQuery(value).toString()
}

function normalizeUrl(): void {
  if (strictStateFromQuery(route.query)) return
  void router
    .replace({ query: Object.fromEntries(serializeLiveMemoryQuery(state.value)) })
    .catch(() => undefined)
}

onMounted(normalizeUrl)

watch(
  state,
  (next) => {
    if (!import.meta.client) return
    const current = strictStateFromQuery(route.query)
    if (current && serialized(next) === serialized(current)) {
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
