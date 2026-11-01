<script setup lang="ts">
import { computed } from "vue"
import { ChevronRight } from "@lucide/vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernLifecyclePill from "@/components/console/govern/primitives/GovernLifecyclePill.vue"
import {
  directiveApprovalState,
  directiveCandidate,
  directiveCheckSummary,
  directiveCheckTarget,
  directiveLive,
  directivePrimaryState,
  directiveRowEdge,
  type Directive,
} from "@/lib/directive-preview"
import { formatGovernRelative } from "@/lib/govern-format"

const props = defineProps<{
  directive: Directive
  returnTo: string
  selected?: boolean
}>()

const emit = defineEmits<{ open: []; quick: [] }>()

const live = computed(() => directiveLive(props.directive))
const candidate = computed(() => directiveCandidate(props.directive))
const latest = computed(() => props.directive.versions[0] ?? null)
const checks = computed(() => directiveCheckSummary(directiveCheckTarget(props.directive)))
const edge = computed(() => directiveRowEdge(props.directive))

const candidateInfo = computed(() => {
  if (candidate.value) {
    const summary = directiveCheckSummary(candidate.value)
    if (summary.failed > 0) {
      return { text: `${summary.failed} failed check${summary.failed === 1 ? "" : "s"}`, tone: "text-crit" }
    }
    const approval = directiveApprovalState(candidate.value)
    if (approval.state === "waiting") {
      return { text: `waiting ${approval.waiting} approval${approval.waiting === 1 ? "" : "s"}`, tone: "text-warn" }
    }
    return { text: "ready to promote", tone: "text-ok" }
  }
  if (latest.value?.state === "rejected") return { text: "Rejected", tone: "text-crit" }
  return { text: "No candidate", tone: "text-fg-3" }
})

const candidateVersion = computed(() => candidate.value?.version ?? (latest.value?.state === "rejected" ? latest.value.version : null))

const checkTone = computed(() =>
  checks.value.tone === "destructive"
    ? "text-crit"
    : checks.value.tone === "warning"
      ? "text-warn"
      : checks.value.tone === "success"
        ? "text-ok"
        : "text-fg-3",
)

const checkScope = computed(() => (candidate.value ? "candidate" : live.value ? "live" : "no version"))

const approvalInfo = computed(() => {
  if (!candidate.value) return { primary: "—", secondary: live.value ? "No candidate" : "No version", tone: "text-fg-3" }
  const approval = directiveApprovalState(candidate.value)
  if (approval.state === "blocked") return { primary: "Blocked", secondary: "check failed", tone: "text-crit" }
  if (approval.state === "approved") return { primary: "Approved", secondary: `${approval.approved}/${approval.required} recorded`, tone: "text-ok" }
  return {
    primary: `Needs ${approval.waiting}`,
    secondary: `waiting ${approval.waitingLabel}`,
    tone: "text-warn",
  }
})

const agentSummary = computed(() => {
  const names = props.directive.agents.map((agent) => agent.name)
  if (names.length <= 2) return names.join(", ")
  return `${names.slice(0, 2).join(", ")} +${names.length - 2}`
})

function open(): void {
  emit("open")
}
</script>

<template>
  <tr
    :data-edge="edge ?? undefined"
    :data-selected="selected ? 'true' : undefined"
    tabindex="0"
    :aria-label="`Open directive ${directive.name}`"
    @click="open"
    @keydown.enter.prevent="open"
    @keydown.space.prevent="emit('quick')"
  >
    <td class="min-w-56">
      <div class="flex min-w-0 flex-col gap-0.5">
        <span class="truncate text-sm font-medium text-fg-1">{{ directive.name }}</span>
        <span class="flex min-w-0 items-center gap-1.5 text-xs text-fg-3">
          <span class="truncate">{{ directive.scope.area }}</span>
          <span aria-hidden="true">·</span>
          <GovernCopyId :id="directive.id" label="Directive ID" truncate />
        </span>
      </div>
    </td>
    <td>
      <GovernLifecyclePill :state="directivePrimaryState(directive)" />
    </td>
    <td class="min-w-28">
      <div v-if="live" class="flex flex-col gap-0.5">
        <span class="font-mono text-xs text-fg-1 tabular-nums">{{ live.version }}</span>
        <span class="text-[0.6875rem] text-fg-3">live {{ formatGovernRelative(live.liveFrom) }}</span>
      </div>
      <span v-else class="text-xs text-fg-3">No live version</span>
    </td>
    <td class="min-w-32">
      <div v-if="candidateVersion" class="flex flex-col gap-0.5">
        <span class="font-mono text-xs text-fg-1 tabular-nums">{{ candidateVersion }}</span>
        <span class="text-[0.6875rem]" :class="candidateInfo.tone">{{ candidateInfo.text }}</span>
      </div>
      <span v-else class="text-xs text-fg-3">{{ candidateInfo.text }}</span>
    </td>
    <td class="min-w-24">
      <div class="flex flex-col gap-0.5">
        <span class="font-mono text-xs tabular-nums" :class="checkTone">{{ checks.label }}</span>
        <span class="text-[0.6875rem] text-fg-3">{{ checkScope }}</span>
      </div>
    </td>
    <td class="min-w-28">
      <div class="flex flex-col gap-0.5">
        <span class="font-mono text-xs tabular-nums" :class="approvalInfo.tone">{{ approvalInfo.primary }}</span>
        <span class="text-[0.6875rem] text-fg-3">{{ approvalInfo.secondary }}</span>
      </div>
    </td>
    <td class="min-w-28">
      <div v-if="latest" class="flex flex-col gap-0.5">
        <span class="text-xs text-fg-2">{{ formatGovernRelative(latest.createdAt) }}</span>
        <span class="truncate text-[0.6875rem] text-fg-3">{{ latest.author }}</span>
      </div>
      <span v-else class="text-xs text-fg-3">—</span>
    </td>
    <td class="min-w-32">
      <div class="flex max-w-40 flex-col gap-0.5">
        <span class="truncate text-xs text-fg-2">{{ agentSummary }}</span>
        <span class="text-[0.6875rem] text-fg-3">{{ directive.agents.length }} {{ directive.agents.length === 1 ? "agent" : "agents" }}</span>
      </div>
    </td>
    <td class="w-8 pr-3 text-right">
      <button
        type="button"
        class="ix-row-action"
        :aria-label="`Open ${directive.name}`"
        @click.stop="open"
      >
        <ChevronRight :size="14" :stroke-width="1.9" aria-hidden="true" />
      </button>
    </td>
  </tr>
</template>
