<script setup lang="ts">
import { onMounted, ref, watch } from "vue"
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router"
import PolicyListView from "@/components/console/policy/list/PolicyListView.vue"
import {
  parsePolicyListQueryV2,
  serializePolicyListQueryV2,
  type PolicyListStateV2,
} from "@/lib/govern-query"

const SNAPSHOT_KEY = "ibex:policy-list:return"

type Snapshot = { path: string; scrollY: number }

const route = useRoute()
const router = useRouter()
const state = ref<PolicyListStateV2>(parsePolicyListQueryV2(route.query))
const returnTo = ref(route.fullPath)

useHead({ title: "Policies · IBEX Console" })

function serialized(value: PolicyListStateV2): string {
  return serializePolicyListQueryV2(value).toString()
}

function queryFrom(value: PolicyListStateV2): Record<string, string> {
  return Object.fromEntries(serializePolicyListQueryV2(value))
}

function isSearchOnly(next: PolicyListStateV2): boolean {
  const current = parsePolicyListQueryV2(route.query)
  const withoutSearch = (value: PolicyListStateV2) => serialized({ ...value, q: "" })
  return withoutSearch(next) === withoutSearch(current) && next.q !== current.q
}

function update(next: PolicyListStateV2): void {
  state.value = next
}

watch(
  state,
  (next) => {
    if (!import.meta.client) return
    if (serialized(next) === serialized(parsePolicyListQueryV2(route.query))) {
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
    if (route.path !== "/policies") return
    const parsed = parsePolicyListQueryV2(route.query)
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
  <PolicyListView :state="state" :return-to="returnTo" @update="update" />
</template>
