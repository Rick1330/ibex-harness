<script setup lang="ts">
import { computed } from "vue"
import { Check, Clock, ShieldAlert, UserRound } from "@lucide/vue"
import type { DirectiveApproval, DirectiveApprovalState } from "@/lib/directive-preview"
import { formatGovernStamp, formatGovernWait } from "@/lib/govern-format"

const props = defineProps<{
  approval: DirectiveApprovalState
  approvals: DirectiveApproval[]
  author: string
}>()

const tone = computed(() => {
  if (props.approval.state === "blocked") return { icon: ShieldAlert, label: "Blocked", classes: "border-transparent bg-transparent text-crit" }
  if (props.approval.state === "approved") return { icon: Check, label: "Approved", classes: "border-transparent bg-transparent text-ok" }
  if (props.approval.state === "waiting") return { icon: Clock, label: "Waiting", classes: "border-transparent bg-transparent text-warn" }
  return { icon: UserRound, label: "No approval required", classes: "border-line bg-raised text-fg-3" }
})

const completedAt = computed(() => {
  const approved = props.approvals.filter((approval) => approval.decision === "approved").at(-1)
  return approved ? formatGovernStamp(approved.at) : "—"
})
</script>

<template>
  <section class="rounded-lg border border-line-subtle bg-surface-1">
    <header class="flex flex-wrap items-center justify-between gap-2 border-b border-line-subtle px-4 py-2.5">
      <div>
        <h3 class="text-sm font-semibold text-fg-1">Approval</h3>
        <p class="mt-0.5 text-xs text-fg-3">A person other than the author must approve before promotion.</p>
      </div>
      <span class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-xs font-medium" :class="tone.classes">
        <component :is="tone.icon" :size="11" :stroke-width="2" aria-hidden="true" />
        {{ tone.label }}
      </span>
    </header>

    <dl v-if="approval.state !== 'none'" class="grid grid-cols-2 gap-px bg-line-subtle max-sm:grid-cols-1">
      <div class="bg-surface-1 px-4 py-2.5">
        <dt class="text-[0.6875rem] text-fg-3">Required</dt>
        <dd class="mt-0.5 font-mono text-sm text-fg-1 tabular-nums">
          {{ approval.approved }} of {{ approval.required }} approval{{ approval.required === 1 ? "" : "s" }}
        </dd>
      </div>
      <div class="bg-surface-1 px-4 py-2.5">
        <dt class="text-[0.6875rem] text-fg-3">{{ approval.state === "waiting" ? "Waiting" : "Completed" }}</dt>
        <dd class="mt-0.5 font-mono text-sm text-fg-1 tabular-nums">
          {{ approval.state === "waiting" ? formatGovernWait(approval.waitingSince) : completedAt }}
        </dd>
      </div>
    </dl>

    <div class="space-y-3 px-4 py-3">
      <div v-if="approval.eligible.length">
        <p class="text-[0.6875rem] font-medium tracking-wide text-fg-3 uppercase">Eligible approvers</p>
        <ul class="mt-1.5 flex flex-wrap gap-1.5">
          <li
            v-for="actor in approval.eligible"
            :key="actor"
            class="inline-flex h-6 items-center rounded-full border border-line-subtle bg-raised px-2 text-xs text-fg-2"
          >{{ actor }}</li>
        </ul>
        <p v-if="approval.authorExcluded" class="mt-1.5 flex items-center gap-1.5 text-xs text-warn">
          <ShieldAlert :size="12" :stroke-width="1.8" aria-hidden="true" />
          {{ author }} wrote this version and cannot approve it.
        </p>
      </div>

      <div v-if="approvals.length">
        <p class="text-[0.6875rem] font-medium tracking-wide text-fg-3 uppercase">Decisions</p>
        <ul class="mt-1.5 space-y-1">
          <li v-for="entry in approvals" :key="`${entry.actor}-${entry.at}`" class="flex flex-wrap items-baseline gap-x-2 text-xs">
            <span class="font-medium text-fg-1">{{ entry.actor }}</span>
            <span :class="entry.decision === 'approved' ? 'text-ok' : 'text-warn'">
              {{ entry.decision === "approved" ? "approved" : "requested changes" }}
            </span>
            <span class="font-mono text-[0.625rem] text-fg-3">{{ formatGovernStamp(entry.at) }}</span>
          </li>
        </ul>
      </div>

      <p v-else-if="approval.state === 'waiting'" class="text-xs text-fg-3">
        No decision recorded yet. The author cannot satisfy this requirement.
      </p>
    </div>
  </section>
</template>
