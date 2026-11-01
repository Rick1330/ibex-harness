<script setup lang="ts">
import { computed } from "vue"
import { CircleCheck, CircleDashed } from "@lucide/vue"
import {
  directiveApprovalState,
  directiveCandidate,
  directiveLive,
  type Directive,
  type DirectiveVersion,
} from "@/lib/directive-preview"
import { formatGovernClock, formatGovernShortDate } from "@/lib/govern-format"

type StepStatus = "done" | "current" | "pending"

type Step = {
  key: string
  label: string
  detail: string
  meta: string | null
  status: StepStatus
}

const props = defineProps<{ directive: Directive }>()

const candidate = computed(() => directiveCandidate(props.directive))
const live = computed(() => directiveLive(props.directive))
const focus = computed<DirectiveVersion | null>(() => candidate.value ?? live.value ?? props.directive.versions[0] ?? null)

function stamp(value: string | null): string | null {
  return value ? `${formatGovernShortDate(value)} · ${formatGovernClock(value)}` : null
}

const steps = computed<Step[]>(() => {
  const version = focus.value
  if (!version) return []

  const isCandidate = version.state === "candidate"
  const checks = version.checks.filter((check) => check.id !== "approval")
  const recordedChecks = checks.filter((check) => check.at !== null)
  const latestCheck = [...recordedChecks].sort((left, right) => Date.parse(right.at ?? "") - Date.parse(left.at ?? ""))[0] ?? null
  const approval = directiveApprovalState(version)
  const approvalRecord = version.approvals.filter((entry) => entry.decision === "approved").at(-1) ?? null
  const approvalDone = isCandidate ? approval.state === "approved" : Boolean(version.approvedBy)
  const checksDone = checks.length > 0 && !checks.some((check) => check.state === "failed" || check.state === "pending")
  const checksLabel = checks.length
    ? `${checks.filter((check) => check.state === "passed").length}/${checks.length} validation checks passed`
    : "No check records"

  const approvalDetail = approvalRecord
    ? `Approved by ${approvalRecord.actor}`
    : isCandidate
      ? approval.state === "waiting"
        ? `${approval.approved} of ${approval.required} approvals recorded`
        : "Awaiting approval"
      : version.approvedBy
        ? `Approved by ${version.approvedBy}`
        : "No approval record"

  const approvalMeta = approvalRecord ? stamp(approvalRecord.at) : isCandidate && approval.state === "waiting" ? `Waiting ${approval.waitingLabel}` : stamp(version.approvedAt)

  const liveDetail =
    version.state === "live"
      ? `Live since ${formatGovernShortDate(version.liveFrom)}`
      : version.state === "superseded" || version.state === "rolled_back"
        ? `Was live ${formatGovernShortDate(version.liveFrom)} – ${formatGovernShortDate(version.liveTo)}`
        : "Promotes after approval"

  const createdAt = stamp(version.createdAt)

  return [
    {
      key: "draft",
      label: "Draft",
      detail: `Created by ${version.author}`,
      meta: createdAt,
      status: "done",
    },
    {
      key: "submitted",
      label: "Submitted",
      detail: isCandidate ? "Open for approval" : "Sent for approval",
      meta: createdAt,
      status: "done",
    },
    {
      key: "checks",
      label: "Checks",
      detail: checksLabel,
      meta: latestCheck ? `${latestCheck.actor ?? "Check runner"} · ${stamp(latestCheck.at)}` : checks.length ? null : "Not configured",
      status: checksDone ? "done" : isCandidate ? "pending" : "done",
    },
    {
      key: "approval",
      label: "Approval",
      detail: approvalDetail,
      meta: approvalMeta,
      status: approvalDone ? "done" : isCandidate ? "current" : "pending",
    },
    {
      key: "live",
      label: "Live",
      detail: liveDetail,
      meta: version.state === "live" || version.state === "superseded" || version.state === "rolled_back" ? stamp(version.liveFrom) : null,
      status:
        version.state === "live" || version.state === "superseded" || version.state === "rolled_back"
          ? "done"
          : isCandidate && approvalDone
            ? "current"
            : "pending",
    },
  ]
})

const focusLabel = computed(() => (focus.value ? `Path for ${focus.value.version}` : "No version yet"))
</script>

<template>
  <section
    v-if="steps.length"
    class="min-w-0 rounded-lg border border-line-subtle bg-surface-1 p-4"
    aria-labelledby="promotion-steps-title"
  >
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <h2 id="promotion-steps-title" class="text-xs font-semibold text-fg-1">Promotion path</h2>
      <p class="text-[0.6875rem] leading-4 text-fg-3">{{ focusLabel }}</p>
    </div>
    <ol class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-5 sm:gap-0">
      <li
        v-for="(step, index) in steps"
        :key="step.key"
        class="relative flex min-w-0 gap-2.5 sm:flex-col sm:gap-1.5 sm:pr-4"
        :aria-current="step.status === 'current' ? 'step' : undefined"
      >
        <div class="flex items-center sm:w-full">
          <span
            class="inline-flex size-5 shrink-0 items-center justify-center rounded-full border"
            :class="
              step.status === 'done'
                ? 'border-transparent bg-transparent text-ok'
                : step.status === 'current'
                  ? 'border-accent-memory/40 bg-accent-memory/10 text-accent-memory'
                  : 'border-line-subtle bg-surface-2 text-fg-off'
            "
          >
            <CircleCheck v-if="step.status === 'done'" :size="12" :stroke-width="2" aria-hidden="true" />
            <CircleDashed v-else :size="12" :stroke-width="2" aria-hidden="true" />
          </span>
          <span v-if="index < steps.length - 1" class="ml-1.5 hidden h-px flex-1 bg-line-subtle sm:block" aria-hidden="true" />
        </div>
        <div class="min-w-0">
          <p class="text-xs font-medium" :class="step.status === 'current' ? 'text-fg-1' : step.status === 'done' ? 'text-fg-2' : 'text-fg-3'">
            {{ step.label }}
            <span v-if="step.status === 'current'" class="sr-only">(current step)</span>
          </p>
          <p class="truncate text-[0.6875rem] leading-4 text-fg-3">{{ step.detail }}</p>
          <p v-if="step.meta" class="truncate text-[0.6875rem] leading-4 text-fg-3">{{ step.meta }}</p>
        </div>
      </li>
    </ol>
  </section>
</template>
