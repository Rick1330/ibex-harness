<script setup lang="ts">
import { computed } from "vue"
import { ArrowUpRight, ShieldAlert, TriangleAlert } from "@lucide/vue"
import GovernApprovalBlock from "@/components/console/govern/primitives/GovernApprovalBlock.vue"
import GovernCheckList from "@/components/console/govern/primitives/GovernCheckList.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernHashTag from "@/components/console/govern/primitives/GovernHashTag.vue"
import GovernLifecyclePill from "@/components/console/govern/primitives/GovernLifecyclePill.vue"
import {
  directiveApprovalState,
  directiveById,
  directiveCandidate,
  directiveCheckSummary,
  directiveCheckTarget,
  directiveLive,
  type DirectiveTab,
} from "@/lib/directive-preview"
import { formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"

const props = defineProps<{
  directiveId: string
  returnTo: string
}>()

const emit = defineEmits<{ open: [] }>()

const directive = computed(() => directiveById(props.directiveId))
const live = computed(() => (directive.value ? directiveLive(directive.value) : null))
const candidate = computed(() => (directive.value ? directiveCandidate(directive.value) : null))
const checks = computed(() => (directive.value ? directiveCheckSummary(directiveCheckTarget(directive.value)) : directiveCheckSummary(null)))
const approval = computed(() => directiveApprovalState(candidate.value))
const focusChecks = computed(() => candidate.value?.checks ?? live.value?.checks ?? [])

function href(tab: DirectiveTab): string {
  if (!directive.value) return props.returnTo
  const params = new URLSearchParams()
  if (tab !== "overview") params.set("tab", tab)
  if (props.returnTo) params.set("return", props.returnTo)
  const query = params.toString()
  return `/directives/${encodeURIComponent(directive.value.id)}${query ? `?${query}` : ""}`
}
</script>

<template>
  <div v-if="directive" class="flex min-h-0 flex-col gap-5 p-5 pt-2">
    <div class="min-w-0">
      <div class="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
        <h2 class="min-w-0 truncate text-lg leading-6 font-semibold text-fg-1">{{ directive.name }}</h2>
        <GovernLifecyclePill v-if="candidate" state="candidate" />
        <GovernLifecyclePill v-else-if="live" state="live" />
      </div>
      <p class="mt-1 line-clamp-2 text-xs leading-4 text-fg-3">{{ directive.description }}</p>
      <p class="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-fg-3">
        <span class="font-mono text-[0.6875rem]">{{ directive.scope.org }} · {{ directive.scope.workspace }}</span>
        <span aria-hidden="true">·</span>
        <span>{{ directive.scope.area }}</span>
        <span aria-hidden="true">·</span>
        <GovernCopyId :id="directive.id" label="Directive ID" />
      </p>
    </div>

    <div class="grid grid-cols-2 gap-2">
      <div class="rounded-lg border border-line-subtle bg-surface-1 px-3 py-2">
        <p class="text-[0.6875rem] text-fg-3">Live</p>
        <p class="mt-0.5 font-mono text-sm font-semibold text-fg-1 tabular-nums">{{ live?.version ?? "None" }}</p>
        <p class="text-[0.6875rem] text-fg-3">{{ live?.liveFrom ? `since ${formatGovernRelative(live.liveFrom)}` : "no live version" }}</p>
      </div>
      <div class="rounded-lg border border-line-subtle bg-surface-1 px-3 py-2">
        <p class="text-[0.6875rem] text-fg-3">Candidate</p>
        <p class="mt-0.5 font-mono text-sm font-semibold text-fg-1 tabular-nums">{{ candidate?.version ?? "None" }}</p>
        <p class="text-[0.6875rem]" :class="checks.failed ? 'text-crit' : checks.pending ? 'text-warn' : 'text-fg-3'">
          {{ checks.label }}
        </p>
      </div>
    </div>

    <div v-if="candidate">
      <p class="mb-1.5 text-xs font-medium text-fg-3">Candidate checks</p>
      <GovernCheckList :items="focusChecks" :empty-label="`${candidate.version} has no checks recorded.`" />
    </div>

    <GovernApprovalBlock
      v-if="candidate && approval.state !== 'none'"
      :approval="approval"
      :approvals="candidate.approvals"
      :author="candidate.author"
    />

    <div v-if="candidate?.riskFlags.length">
      <p class="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-warn">
        <TriangleAlert :size="12" :stroke-width="1.9" aria-hidden="true" />
        Risk flags
      </p>
      <ul class="space-y-1 rounded-lg border border-warn/30 bg-warn-tint/50 px-3 py-2 text-xs leading-5 text-fg-2">
        <li v-for="flag in candidate.riskFlags" :key="flag" class="flex items-start gap-1.5">
          <span class="mt-1.5 size-1 shrink-0 rounded-full bg-warn" aria-hidden="true" />
          {{ flag }}
        </li>
      </ul>
    </div>

    <div v-if="live" class="rounded-lg border border-line-subtle bg-surface-1 px-3 py-2">
      <p class="text-[0.6875rem] text-fg-3">Live version hash</p>
      <div class="mt-1 flex flex-wrap items-center justify-between gap-2">
        <GovernHashTag :hash="live.hash" />
        <span class="text-[0.6875rem] text-fg-3">{{ formatGovernStamp(live.liveFrom) }}</span>
      </div>
    </div>

    <div class="flex flex-wrap items-center gap-2 border-t border-line-subtle pt-3">
      <NuxtLink :to="href('overview')" class="ix-button-primary h-8 px-3 text-xs" @click="emit('open')">
        Open directive
        <ArrowUpRight :size="12" :stroke-width="1.9" aria-hidden="true" />
      </NuxtLink>
      <NuxtLink :to="href('diff')" class="ix-button-secondary h-8 px-3 text-xs">Diff</NuxtLink>
      <NuxtLink :to="href('promotion')" class="ix-button-secondary h-8 px-3 text-xs">Promotion</NuxtLink>
      <NuxtLink :to="href('audit')" class="ix-button-secondary h-8 px-3 text-xs">Audit</NuxtLink>
    </div>

    <p class="flex items-start gap-1.5 text-[0.6875rem] leading-4 text-fg-3">
      <ShieldAlert :size="12" :stroke-width="1.8" class="mt-0.5 shrink-0" aria-hidden="true" />
      Quick look is read-only. Promotion and rollback require a privileged write contract.
    </p>
  </div>
</template>
