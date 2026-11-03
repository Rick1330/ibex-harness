<script setup lang="ts">
import { onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import DirectiveListView from "@/components/console/directive/live/DirectiveListView.vue"
import {
  parseLiveDirectiveListQuery,
  parseLiveDirectiveListQueryLenient,
  serializeLiveDirectiveListQuery,
  type LiveDirectiveListQuery,
} from "~~/shared/operator/directive-query"

const route = useRoute()
const router = useRouter()
const state = ref<LiveDirectiveListQuery>(stateFromQuery(route.query))
const returnTo = ref(route.fullPath)

useHead({ title: "Directives · IBEX Console" })

function strictStateFromQuery(query: Record<string, unknown>): LiveDirectiveListQuery | null {
  try {
    return parseLiveDirectiveListQuery(query)
  } catch {
    return null
  }
}

function stateFromQuery(query: Record<string, unknown>): LiveDirectiveListQuery {
  return strictStateFromQuery(query) ?? parseLiveDirectiveListQueryLenient(query)
}

function serialized(value: LiveDirectiveListQuery): string {
  return serializeLiveDirectiveListQuery(value).toString()
}

function normalizeUrl(): void {
  if (strictStateFromQuery(route.query)) return
  void router
    .replace({ query: Object.fromEntries(serializeLiveDirectiveListQuery(state.value)) })
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
      .replace({ query: Object.fromEntries(serializeLiveDirectiveListQuery(next)) })
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
    if (route.path !== "/directives") return
    const strict = strictStateFromQuery(route.query)
    const parsed = strict ?? parseLiveDirectiveListQueryLenient(route.query)
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
  <DirectiveListView :state="state" :return-to="returnTo" @update="state = $event" />
</template>
