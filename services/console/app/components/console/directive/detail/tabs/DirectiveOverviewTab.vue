<script setup lang="ts">
import { computed } from "vue"
import { ArrowRight, CircleAlert, ExternalLink, RotateCcw, TriangleAlert } from "@lucide/vue"
import GovernApprovalBlock from "@/components/console/govern/primitives/GovernApprovalBlock.vue"
import GovernCheckList from "@/components/console/govern/primitives/GovernCheckList.vue"
import GovernDiffSummaryBar from "@/components/console/govern/primitives/GovernDiffSummaryBar.vue"
import GovernEmptyValue from "@/components/console/govern/primitives/GovernEmptyValue.vue"
import GovernHashTag from "@/components/console/govern/primitives/GovernHashTag.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import GovernLifecyclePill from "@/components/console/govern/primitives/GovernLifecyclePill.vue"
import GovernVersionTag from "@/components/console/govern/primitives/GovernVersionTag.vue"
import {
  DIRECTIVE_EVENT_LABELS,
  directiveApprovalState,
  directiveAuditEvents,
  directiveCandidate,
  directiveCheckSummary,
  directiveCheckTarget,
  directiveEventHref,
  directiveLive,
  directiveRollbackTarget,
  directiveVersionDiff,
  type Directive,
  type DirectiveTab,
} from "@/lib/directive-preview"
import { formatGovernDate, formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"

const props = defineProps<{ directive: Directive }>()
const emit = defineEmits<{ tab: [tab: DirectiveTab] }>()

const live = computed(() => directiveLive(props.directive))
const candidate = computed(() => directiveCandidate(props.directive))
const rollbackTarget = computed(() => directiveRollbackTarget(props.directive))
const target = computed(() => directiveCheckTarget(props.directive))
const checks = computed(() => directiveCheckSummary(target.value))
const events = computed(() => directiveAuditEvents(props.directive).slice(0, 4))
const candidateDiff = computed(() => (candidate.value ? directiveVersionDiff(props.directive, candidate.value) : null))
const changedSections = computed(() => candidateDiff.value?.sections.filter((section) => section.changed) ?? [])
const riskFlags = computed(() => {
  const version = candidate.value ?? live.value
  return version?.riskFlags ?? []
})
</script>

<template>
  <div class="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
    <div class="flex min-w-0 flex-col gap-4">
      <section class="min-w-0 rounded-lg border border-line-subtle bg-surface-1" aria-labelledby="directive-state-title">
        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-line-subtle px-4 py-2.5">
          <h2 id="directive-state-title" class="text-xs font-semibold text-fg-1">Current state</h2>
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded text-xs text-fg-3 transition-colors hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            @click="emit('tab', 'versions')"
          >
            Versions
            <ArrowRight :size="12" :stroke-width="1.9" aria-hidden="true" />
          </button>
        </div>

        <div class="grid gap-px bg-line-subtle sm:grid-cols-2">
          <div class="min-w-0 bg-surface-1 px-4 py-3">
            <div class="flex items-center gap-2">
              <GovernVersionTag label="Live" :value="live?.version ?? '—'" :tone="live ? 'default' : 'muted'" />
              <GovernLifecyclePill v-if="live" :state="live.state" />
            </div>
            <dl class="mt-2.5 space-y-1.5 text-xs leading-4">
              <div class="flex items-baseline justify-between gap-3">
                <dt class="text-fg-3">Live since</dt>
                <dd class="truncate text-fg-2">{{ live?.liveFrom ? formatGovernDate(live.liveFrom) : "Never promoted" }}</dd>
              </div>
              <div class="flex items-baseline justify-between gap-3">
                <dt class="text-fg-3">Author</dt>
                <dd class="truncate text-fg-2">{{ live?.author ?? "—" }}</dd>
              </div>
              <div class="flex items-baseline justify-between gap-3">
                <dt class="text-fg-3">Approved by</dt>
                <dd class="truncate text-fg-2">{{ live?.approvedBy ?? "Not recorded" }}</dd>
              </div>
              <div class="flex items-center justify-between gap-3">
                <dt class="text-fg-3">Rollback target</dt>
                <dd class="min-w-0">
                  <button
                    v-if="rollbackTarget"
                    type="button"
                    class="rounded font-mono text-[0.6875rem] text-fg-2 underline decoration-line-strong underline-offset-3 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                    @click="emit('tab', 'promotion')"
                  >{{ rollbackTarget.version }}</button>
                  <span v-else class="text-fg-3">None</span>
                </dd>
              </div>
            </dl>
            <GovernHashTag v-if="live" class="mt-2.5" :hash="live.hash" label="live digest" />
          </div>

          <div class="min-w-0 bg-surface-1 px-4 py-3">
            <div class="flex items-center gap-2">
              <GovernVersionTag label="Candidate" :value="candidate?.version ?? '—'" :tone="candidate ? 'default' : 'muted'" />
              <GovernLifecyclePill v-if="candidate" :state="candidate.state" />
            </div>
            <template v-if="candidate">
              <dl class="mt-2.5 space-y-1.5 text-xs leading-4">
                <div class="flex items-baseline justify-between gap-3">
                  <dt class="text-fg-3">Author</dt>
                  <dd class="truncate text-fg-2">{{ candidate.author }}</dd>
                </div>
                <div class="flex items-baseline justify-between gap-3">
                  <dt class="text-fg-3">Opened</dt>
                  <dd class="truncate text-fg-2" :title="formatGovernStamp(candidate.createdAt)">{{ formatGovernRelative(candidate.createdAt) }}</dd>
                </div>
                <div class="flex items-baseline justify-between gap-3">
                  <dt class="text-fg-3">Checks</dt>
                  <dd class="truncate font-mono tabular-nums" :class="directiveCheckSummary(candidate).failed ? 'text-crit' : 'text-fg-2'">
                    {{ directiveCheckSummary(candidate).label }}
                  </dd>
                </div>
                <div class="flex items-baseline justify-between gap-3">
                  <dt class="text-fg-3">Approvals</dt>
                  <dd class="truncate font-mono tabular-nums text-fg-2">
                    {{ directiveApprovalState(candidate).required ? `${directiveApprovalState(candidate).approved}/${directiveApprovalState(candidate).required}` : "Not required" }}
                  </dd>
                </div>
              </dl>
              <GovernHashTag class="mt-2.5" :hash="candidate.hash" label="candidate digest" />
            </template>
            <p v-else class="mt-3 text-xs leading-5 text-fg-3">No candidate is open. The live version serves every attached agent.</p>
          </div>
        </div>

        <div v-if="candidate" class="border-t border-line-subtle px-4 py-3">
          <GovernApprovalBlock
            :approval="directiveApprovalState(candidate)"
            :approvals="candidate.approvals"
            :author="candidate.author"
          />
        </div>
      </section>

      <section
        v-if="candidateDiff"
        class="min-w-0 rounded-lg border border-line-subtle bg-surface-1"
        aria-labelledby="directive-change-title"
      >
        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-line-subtle px-4 py-2.5">
          <div class="min-w-0">
            <h2 id="directive-change-title" class="text-xs font-semibold text-fg-1">What the candidate changes</h2>
            <p class="mt-0.5 text-[0.6875rem] leading-4 text-fg-3">Compared with {{ live?.version ?? "the previous version" }}.</p>
          </div>
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded text-xs text-fg-3 transition-colors hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            @click="emit('tab', 'diff')"
          >
            Open diff
            <ArrowRight :size="12" :stroke-width="1.9" aria-hidden="true" />
          </button>
        </div>
        <div class="px-4 py-3">
          <GovernDiffSummaryBar
            :summary="candidateDiff.summary"
            :from="live?.version ?? null"
            :to="candidate?.version ?? null"
          />
          <ul v-if="changedSections.length" class="mt-3 space-y-2">
            <li v-for="section in changedSections" :key="section.id" class="rounded-lg border border-line-subtle bg-surface-2/50 px-3 py-2">
              <div class="flex items-center justify-between gap-3">
                <span class="text-xs font-medium text-fg-1">{{ section.label }}</span>
                <span class="font-mono text-[0.625rem] text-fg-3 tabular-nums">+{{ section.added }} −{{ section.removed }}</span>
              </div>
              <p v-for="line in section.lines.filter((entry) => entry.type !== 'same').slice(0, 2)" :key="`${section.id}-${line.text}`" class="mt-1 truncate font-mono text-[0.6875rem] leading-4" :class="line.type === 'added' ? 'text-diff-add' : 'text-diff-remove'">
                <span aria-hidden="true">{{ line.type === "added" ? "+" : "−" }}</span> {{ line.text }}
              </p>
            </li>
          </ul>
          <p v-else class="mt-3 text-xs text-fg-3">The candidate text matches the live version.</p>
          <p v-if="candidate?.summary" class="mt-3 border-t border-line-subtle pt-2.5 text-xs leading-5 text-fg-2">{{ candidate.summary }}</p>
        </div>
      </section>


      <section class="min-w-0 rounded-lg border border-line-subtle bg-surface-1" aria-labelledby="directive-live-text-title">
        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-line-subtle px-4 py-2.5">
          <div>
            <h2 id="directive-live-text-title" class="text-xs font-semibold text-fg-1">Current live directive</h2>
            <p class="mt-0.5 text-[0.6875rem] leading-4 text-fg-3">The exact text agents receive today.</p>
          </div>
          <GovernVersionTag v-if="live" label="Live" :value="live.version" tone="default" />
        </div>
        <div v-if="live" class="divide-y divide-line-subtle">
          <details v-for="section in live.sections" :key="section.id" class="group px-4 py-2.5" open>
            <summary class="flex cursor-pointer list-none items-center justify-between gap-2 text-xs font-medium text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory">
              {{ section.label }}
              <span class="text-[0.625rem] font-normal text-fg-3 group-open:hidden">Show</span>
              <span class="hidden text-[0.625rem] font-normal text-fg-3 group-open:inline">Hide</span>
            </summary>
            <ul class="mt-1.5 space-y-1">
              <li v-for="line in section.lines" :key="line" class="text-[0.8125rem] leading-5 text-fg-2">{{ line }}</li>
            </ul>
          </details>
        </div>
        <p v-else class="px-4 py-3 text-xs text-fg-3">No version has served traffic yet, so there is no live text.</p>
      </section>
      <section class="min-w-0 rounded-lg border border-line-subtle bg-surface-1" aria-labelledby="directive-scope-title">
        <div class="border-b border-line-subtle px-4 py-2.5">
          <h2 id="directive-scope-title" class="text-xs font-semibold text-fg-1">Scope and attachment</h2>
        </div>
        <div class="grid gap-4 px-4 py-3 sm:grid-cols-2">
          <dl class="min-w-0 space-y-1.5 text-xs leading-4">
            <div class="flex items-baseline justify-between gap-3">
              <dt class="text-fg-3">Organization</dt>
              <dd class="truncate font-mono text-[0.6875rem] text-fg-2">{{ directive.scope.org }}</dd>
            </div>
            <div class="flex items-baseline justify-between gap-3">
              <dt class="text-fg-3">Workspace</dt>
              <dd class="truncate font-mono text-[0.6875rem] text-fg-2">{{ directive.scope.workspace }}</dd>
            </div>
            <div class="flex items-baseline justify-between gap-3">
              <dt class="text-fg-3">Area</dt>
              <dd class="truncate text-fg-2">{{ directive.scope.area }}</dd>
            </div>
          </dl>
          <div class="min-w-0">
            <p class="text-xs text-fg-3">Agents this directive reaches</p>
            <ul class="mt-1.5 space-y-1">
              <li v-for="agent in directive.agents" :key="agent.id" class="flex items-center justify-between gap-2 text-xs">
                <NuxtLink :to="`/agents/${agent.id}`" class="truncate text-fg-2 underline decoration-line-strong underline-offset-3 hover:text-fg-1">{{ agent.name }}</NuxtLink>
                <span class="shrink-0 font-mono text-[0.625rem] text-fg-3">{{ agent.id }}</span>
              </li>
              <li v-if="directive.agents.length === 0"><GovernEmptyValue reason="No agents attached" /></li>
            </ul>
          </div>
        </div>
      </section>
    </div>

    <div class="flex min-w-0 flex-col gap-4">
      <section v-if="riskFlags.length" class="min-w-0 rounded-lg border border-warn/30 bg-warn-tint/30 p-4" aria-labelledby="directive-risk-title">
        <h2 id="directive-risk-title" class="flex items-center gap-1.5 text-xs font-semibold text-warn">
          <TriangleAlert :size="13" :stroke-width="1.9" aria-hidden="true" />
          Risk flags on {{ candidate?.version ?? live?.version }}
        </h2>
        <ul class="mt-2 space-y-1.5">
          <li v-for="flag in riskFlags" :key="flag" class="flex items-start gap-1.5 text-xs leading-5 text-fg-2">
            <CircleAlert :size="12" :stroke-width="1.9" class="mt-1 shrink-0 text-warn" aria-hidden="true" />
            {{ flag }}
          </li>
        </ul>
        <button
          type="button"
          class="mt-2.5 text-xs font-medium text-warn underline decoration-current underline-offset-3 hover:text-fg-1"
          @click="emit('tab', 'promotion')"
        >
          Review promotion checks
        </button>
      </section>


      <section class="min-w-0" aria-labelledby="directive-checks-title">
        <div class="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="directive-checks-title" class="text-xs font-semibold text-fg-1">Promotion checks</h2>
          <span class="font-mono text-[0.6875rem] text-fg-3 tabular-nums">{{ checks.label }}</span>
        </div>
        <GovernCheckList :items="target?.checks ?? []" empty-label="No promotion checks are configured for this version." />
      </section>

      <section class="min-w-0 rounded-lg border border-line-subtle bg-surface-1 p-4" aria-labelledby="directive-rollback-title">
        <h2 id="directive-rollback-title" class="text-xs font-semibold text-fg-1">If you roll back now</h2>
        <template v-if="rollbackTarget && live">
          <p class="mt-2 text-xs leading-5 text-fg-2">
            <span class="font-mono text-fg-1">{{ rollbackTarget.version }}</span> becomes live again.
            <span class="font-mono text-fg-1">{{ live.version }}</span> stays in history, and agents pick up
            {{ rollbackTarget.version }} on their next session.
          </p>
          <p class="mt-1.5 font-mono text-[0.625rem] text-fg-3">{{ rollbackTarget.version }} was live {{ formatGovernDate(rollbackTarget.liveFrom) }} – {{ formatGovernDate(rollbackTarget.liveTo) }}</p>
          <div class="mt-2.5">
            <GovernLockedAction label="Roll back" :icon="RotateCcw" variant="secondary" size="sm" />
          </div>
        </template>
        <p v-else class="mt-2 text-xs leading-5 text-fg-3">
          {{ live ? `${live.version} is the first live version. There is nothing earlier to restore.` : "No version has served traffic yet." }}
        </p>
      </section>

      <section class="min-w-0 rounded-lg border border-line-subtle bg-surface-1 p-4" aria-labelledby="directive-timeline-title">
        <div class="flex items-center justify-between gap-2">
          <h2 id="directive-timeline-title" class="text-xs font-semibold text-fg-1">Version at a glance</h2>
          <button type="button" class="text-[0.6875rem] text-fg-3 underline decoration-line-strong underline-offset-3 hover:text-fg-1" @click="emit('tab', 'versions')">All versions</button>
        </div>
        <ol class="mt-2 space-y-2">
          <li v-for="version in directive.versions.slice(0, 5)" :key="version.version" class="flex items-center gap-2.5">
            <span class="size-1.5 shrink-0 rounded-full" :class="version.state === 'live' ? 'bg-ok' : version.state === 'candidate' ? 'bg-warn' : 'bg-line-strong'" aria-hidden="true" />
            <span class="w-8 shrink-0 font-mono text-[0.6875rem] text-fg-2">{{ version.version }}</span>
            <GovernLifecyclePill :state="version.state" />
            <span class="ml-auto truncate text-[0.6875rem] text-fg-3">{{ formatGovernRelative(version.createdAt) }}</span>
          </li>
        </ol>
      </section>
      <section class="min-w-0 rounded-lg border border-line-subtle bg-surface-1" aria-labelledby="directive-activity-title">
        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-line-subtle px-4 py-2.5">
          <h2 id="directive-activity-title" class="text-xs font-semibold text-fg-1">Recent activity</h2>
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded text-xs text-fg-3 transition-colors hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            @click="emit('tab', 'audit')"
          >
            Full audit
            <ArrowRight :size="12" :stroke-width="1.9" aria-hidden="true" />
          </button>
        </div>
        <ol class="divide-y divide-line-subtle">
          <li v-for="event in events" :key="event.id" class="flex items-start gap-2.5 px-4 py-2.5">
            <span class="mt-1 size-1.5 shrink-0 rounded-full bg-line-strong" aria-hidden="true" />
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                <span class="text-xs font-medium text-fg-1">{{ DIRECTIVE_EVENT_LABELS[event.action] }}</span>
                <GovernVersionTag label="Version" :value="event.version" tone="muted" />
              </div>
              <p class="mt-0.5 text-[0.6875rem] leading-4 text-fg-3">
                <span class="text-fg-2">{{ event.actor }}</span> · <span :title="formatGovernStamp(event.at)">{{ formatGovernRelative(event.at) }}</span>
              </p>
            </div>
            <NuxtLink
              :to="directiveEventHref(event)"
              class="mt-0.5 inline-flex shrink-0 items-center gap-1 rounded text-[0.6875rem] text-fg-3 transition-colors hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
              :aria-label="`Open audit evidence for ${DIRECTIVE_EVENT_LABELS[event.action]}`"
            >
              Evidence
              <ExternalLink :size="11" :stroke-width="1.9" aria-hidden="true" />
            </NuxtLink>
          </li>
        </ol>
      </section>

    </div>
  </div>
</template>
