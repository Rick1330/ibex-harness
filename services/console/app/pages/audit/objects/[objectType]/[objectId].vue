<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useRoute } from "vue-router"
import AuditObjectView from "@/components/console/audit/object/AuditObjectView.vue"
import { AUDIT_TARGET_TYPE_LABELS, type AuditTargetType } from "@/lib/audit-preview"
import { parseAuditObjectQuery, serializeAuditObjectQuery, type AuditObjectState } from "@/lib/govern-query"

const route = useRoute()
const type = computed(() => String(route.params.objectType ?? "") as AuditTargetType)
const id = computed(() => String(route.params.objectId ?? ""))
const validType = computed(() => Object.prototype.hasOwnProperty.call(AUDIT_TARGET_TYPE_LABELS, type.value))
const state = ref<AuditObjectState>(parseAuditObjectQuery(route.query))

watch(
  () => route.query,
  () => {
    if (!route.path.startsWith("/audit/objects/")) return
    state.value = parseAuditObjectQuery(route.query)
  },
)

function update(next: AuditObjectState): void {
  state.value = next
  if (!import.meta.client) return
  void navigateTo({ query: Object.fromEntries(serializeAuditObjectQuery(next)) }, { replace: true })
}

useHead(() => ({ title: `${id.value || "Object"} · Audit history · IBEX Console` }))
</script>

<template>
  <AuditObjectView v-if="validType" :id="id" :type="type" :state="state" @update="update" />
  <section
    v-else
    class="mx-auto w-full max-w-[90rem] rounded-lg border border-line-subtle bg-surface-1 p-6"
    aria-labelledby="audit-object-not-found"
  >
    <NuxtLink to="/audit" class="text-xs text-fg-3 hover:text-fg-1">← Back to the audit log</NuxtLink>
    <h1 id="audit-object-not-found" class="mt-4 text-lg font-semibold text-fg-1">Object type not recognised</h1>
    <p class="mt-1 max-w-[70ch] text-sm leading-5 text-fg-3">
      “{{ type || "This object type" }}” is not an audit target type in this console, so no history is reconstructed.
      Open an event and use its target link to reach a recorded object.
    </p>
    <NuxtLink to="/audit" class="ix-button-secondary mt-4 inline-flex h-8 items-center text-xs">
      Browse recorded events
    </NuxtLink>
  </section>
</template>
