<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
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
const router = useRouter()
const directiveId = computed(() => String(route.params.directiveId ?? ""))
const returnTo = computed(() => safeDirectiveReturn(route.query.return))

const state = ref<LiveDirectiveDetailQuery>(detailStateFromQuery(route.query))
const tab = ref<DetailTab>(tabFromQuery(route.query))

/**
 * One builder for every URL rewrite on this page.
 *
 * `return` is part of the location, not of the view state: dropping it on a tab
 * or range change would send "Back to directives" to an unfiltered first page.
 */
function buildQuery(
  nextState: LiveDirectiveDetailQuery,
  nextTab: DetailTab,
  back: unknown,
): Record<string, string> {
  const query: Record<string, string> = Object.fromEntries(
    serializeLiveDirectiveDetailQuery(nextState),
  )
  if (nextTab !== "versions") query.tab = nextTab
  if (typeof back === "string" && back) query.return = back
  return query
}

watch(
  () => route.query,
  () => {
    if (!route.path.startsWith("/directives/")) return
    const parsed = detailStateFromQuery(route.query)
    const nextTab = tabFromQuery(route.query)
    if (serialized(parsed) !== serialized(state.value)) state.value = parsed
    if (nextTab !== tab.value) tab.value = nextTab
  },
)

watch([state, tab], ([nextState, nextTab]) => {
  if (!import.meta.client) return
  const target = buildQuery(nextState, nextTab, route.query.return)
  const current = buildQuery(
    detailStateFromQuery(route.query),
    tabFromQuery(route.query),
    route.query.return,
  )
  if (JSON.stringify(target) === JSON.stringify(current)) return
  void router.replace({ query: target }).catch(() => undefined)
})

function serialized(value: LiveDirectiveDetailQuery): string {
  return serializeLiveDirectiveDetailQuery(value).toString()
}

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
