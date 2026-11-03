<script setup lang="ts">
import { onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import LiveSessionListView from "@/components/console/session/live/LiveSessionListView.vue"
import {
  parseLiveSessionQuery,
  parseLiveSessionQueryLenient,
  serializeLiveSessionQuery,
  type LiveSessionQuery,
} from "~~/shared/operator/session-query"

const route = useRoute()
const router = useRouter()
const state = ref<LiveSessionQuery>(stateFromQuery(route.query))
const returnTo = ref(route.fullPath)

useHead({ title: "Sessions · IBEX Console" })

function strictStateFromQuery(query: Record<string, unknown>): LiveSessionQuery | null {
  try {
    return parseLiveSessionQuery(query)
  } catch {
    return null
  }
}

// A stale or hand-edited link must not widen the read: keep the filters that
// parse, and let `normalizeUrl` drop the rest from the address bar so it always
// describes the list on screen.
function stateFromQuery(query: Record<string, unknown>): LiveSessionQuery {
  return strictStateFromQuery(query) ?? parseLiveSessionQueryLenient(query)
}

function serialized(value: LiveSessionQuery): string {
  return serializeLiveSessionQuery(value).toString()
}

function normalizeUrl(): void {
  if (strictStateFromQuery(route.query)) return
  void router
    .replace({ query: Object.fromEntries(serializeLiveSessionQuery(state.value)) })
    .then(() => {
      returnTo.value = route.fullPath
    })
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
    const strict = strictStateFromQuery(route.query)
    const parsed = strict ?? parseLiveSessionQueryLenient(route.query)
    // Assigning a fresh object also fires the state watcher, which rewrites the
    // address bar. Returning early on an equal parse would leave a URL that
    // still claims a field the read ignores.
    if (strict && serialized(parsed) === serialized(state.value)) {
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
