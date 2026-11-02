<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useRoute } from "vue-router"
import DirectiveDetailView from "@/components/console/directive/live/DirectiveDetailView.vue"
import { safeDirectiveReturn } from "@/lib/return-to"
import {
  parseLiveDirectiveDetailQuery,
  parseLiveDirectiveDetailQueryLenient,
  serializeLiveDirectiveDetailQuery,
  type LiveDirectiveDetailQuery,
} from "~~/shared/operator/directive-query"

const TABS = ["versions", "usage", "diff", "promotion", "audit"] as const
type DetailTab = (typeof TABS)[number]

const route = useRoute()
const directiveId = computed(() => String(route.params.directiveId ?? ""))
const returnTo = computed(() => safeDirectiveReturn(route.query.return))

const state = ref<LiveDirectiveDetailQuery>(detailStateFromQuery(route.query))
const tab = ref<DetailTab>(tabFromQuery(route.query))

watch(
  () => route.query,
  () => {
    if (!route.path.startsWith("/directives/")) return
    state.value = detailStateFromQuery(route.query)
    tab.value = tabFromQuery(route.query)
  },
)

watch(state, (next) => {
  if (!import.meta.client) return
  const query = Object.fromEntries(serializeLiveDirectiveDetailQuery(next))
  if (tab.value !== "versions") query.tab = tab.value
  void useRouter().replace({ query }).catch(() => undefined)
})

watch(tab, (next) => {
  if (!import.meta.client) return
  const query = Object.fromEntries(serializeLiveDirectiveDetailQuery(state.value))
  if (next !== "versions") query.tab = next
  void useRouter().replace({ query }).catch(() => undefined)
})

function strictDetailState(query: Record<string, unknown>): LiveDirectiveDetailQuery | null {
  try {
    return parseLiveDirectiveDetailQuery(query)
  } catch {
    return null
  }
}

function detailStateFromQuery(query: Record<string, unknown>): LiveDirectiveDetailQuery {
  return strictDetailState(query) ?? parseLiveDirectiveDetailQueryLenient(query)
}

function tabFromQuery(query: Record<string, unknown>): DetailTab {
  const raw = typeof query.tab === "string" ? query.tab : ""
  return (TABS as readonly string[]).includes(raw) ? (raw as DetailTab) : "versions"
}

useHead(() => ({ title: "Directive · IBEX Console" }))
</script>

<template>
  <DirectiveDetailView
    v-model:tab="tab"
    :directive-id="directiveId"
    :state="state"
    :return-to="returnTo"
    @update="state = $event"
  />
</template>
