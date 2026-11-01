<script setup lang="ts">
import { onMounted, ref, watch } from "vue"
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router"
import DirectiveListView from "@/components/console/directive/list/DirectiveListView.vue"
import {
  parseDirectiveListQuery,
  serializeDirectiveListQuery,
  type DirectiveListState,
} from "@/lib/govern-query"

const SNAPSHOT_KEY = "ibex:directive-list:return"

type Snapshot = { path: string; scrollY: number }

const route = useRoute()
const router = useRouter()
const state = ref<DirectiveListState>(parseDirectiveListQuery(route.query))
const returnTo = ref(route.fullPath)

useHead({ title: "Directives · IBEX Console" })

function serialized(value: DirectiveListState): string {
  return serializeDirectiveListQuery(value).toString()
}

function queryFrom(value: DirectiveListState): Record<string, string> {
  return Object.fromEntries(serializeDirectiveListQuery(value))
}

function isSearchOnly(next: DirectiveListState): boolean {
  const current = parseDirectiveListQuery(route.query)
  const withoutSearch = (value: DirectiveListState) => serialized({ ...value, q: "" })
  return withoutSearch(next) === withoutSearch(current) && next.q !== current.q
}

function update(next: DirectiveListState): void {
  state.value = next
}

watch(
  state,
  (next) => {
    if (!import.meta.client) return
    if (serialized(next) === serialized(parseDirectiveListQuery(route.query))) {
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
    if (route.path !== "/directives") return
    const parsed = parseDirectiveListQuery(route.query)
    if (serialized(parsed) === serialized(state.value)) {
      returnTo.value = route.fullPath
      return
    }
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
  <DirectiveListView :state="state" :return-to="returnTo" @update="update" />
</template>
