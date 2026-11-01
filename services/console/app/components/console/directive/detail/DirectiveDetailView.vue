<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import {
  BadgeCheck,
  ChevronLeft,
  ChevronRight,
  Copy,
  Ellipsis,
  ExternalLink,
  FileJson,
  MessageSquareWarning,
  RotateCcw,
  Upload,
} from "@lucide/vue"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import GovernAboutPopover from "@/components/console/govern/primitives/GovernAboutPopover.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernDataSourceChip from "@/components/console/govern/primitives/GovernDataSourceChip.vue"
import GovernLifecyclePill from "@/components/console/govern/primitives/GovernLifecyclePill.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import GovernTabBar from "@/components/console/govern/primitives/GovernTabBar.vue"
import { formatGovernRelative, formatGovernShortDate } from "@/lib/govern-format"
import {
  DIRECTIVE_TABS,
  directiveApprovalState,
  directiveBanner,
  directiveCandidate,
  directiveCheckSummary,
  directiveCheckTarget,
  directiveLive,
  directivePrimaryState,
  directives,
  type Directive,
  type DirectiveTab,
} from "@/lib/directive-preview"
import type { DirectiveDetailDefaults, DirectiveDetailState } from "@/lib/govern-query"
import DirectiveOverviewTab from "./tabs/DirectiveOverviewTab.vue"
import DirectiveVersionsTab from "./tabs/DirectiveVersionsTab.vue"
import DirectiveDiffTab from "./tabs/DirectiveDiffTab.vue"
import DirectivePromotionTab from "./tabs/DirectivePromotionTab.vue"
import DirectiveUsageTab from "./tabs/DirectiveUsageTab.vue"
import DirectiveAuditTab from "./tabs/DirectiveAuditTab.vue"

const props = defineProps<{
  directive: Directive
  returnTo: string
  state: DirectiveDetailState
  defaults: DirectiveDetailDefaults
}>()

const emit = defineEmits<{ update: [state: DirectiveDetailState] }>()

function update(patch: Partial<DirectiveDetailState>): void {
  emit("update", { ...props.state, ...patch })
}

function selectTab(tab: DirectiveTab): void {
  update({ tab })
}

// Prev/next follows the same fixture order as /directives.
const order = computed(() => directives)
const currentIndex = computed(() => order.value.findIndex((directive) => directive.id === props.directive.id))
const prevDirective = computed(() => (currentIndex.value > 0 ? order.value[currentIndex.value - 1]! : null))
const nextDirective = computed(() =>
  currentIndex.value >= 0 && currentIndex.value < order.value.length - 1 ? order.value[currentIndex.value + 1]! : null,
)

function goDirective(id: string): void {
  const query = props.returnTo ? { return: props.returnTo } : {}
  void navigateTo({ path: `/directives/${id}`, query })
}

const live = computed(() => directiveLive(props.directive))
const candidate = computed(() => directiveCandidate(props.directive))
const primaryState = computed(() => directivePrimaryState(props.directive))
const checks = computed(() => directiveCheckSummary(directiveCheckTarget(props.directive)))
const approval = computed(() => directiveApprovalState(candidate.value ?? live.value))
const banner = computed(() => directiveBanner(props.directive))

const bannerTone: Record<string, string> = {
  critical: "border-transparent bg-transparent text-crit",
  warning: "border-transparent bg-transparent text-warn",
  info: "border-line-subtle border-l-line-strong bg-raised text-fg-2",
}

const kpis = computed(() => [
  {
    key: "live",
    label: "Live",
    value: live.value?.version ?? "None",
    helper: live.value?.liveFrom ? `since ${formatGovernShortDate(live.value.liveFrom)}` : "No live version",
    tone: "default" as const,
  },
  {
    key: "candidate",
    label: "Candidate",
    value: candidate.value?.version ?? "None",
    helper: candidate.value ? `${candidate.value.author} · ${formatGovernRelative(candidate.value.createdAt)}` : "No open candidate",
    tone: candidate.value ? ("default" as const) : ("default" as const),
  },
  {
    key: "checks",
    label: "Checks",
    value: checks.value.total ? checks.value.label : "Not configured",
    helper: checks.value.failed
      ? `${checks.value.failed} failed`
      : checks.value.pending
        ? `${checks.value.pending} pending`
        : "Every check reported",
    tone: checks.value.failed ? ("critical" as const) : checks.value.pending ? ("warning" as const) : ("default" as const),
  },
  {
    key: "approvals",
    label: "Approvals",
    value: approval.value.required ? `${approval.value.approved}/${approval.value.required}` : "Not required",
    helper: approval.value.state === "waiting" ? `Waiting ${approval.value.waitingLabel}` : approval.value.state === "blocked" ? "Blocked by a failed check" : "No approval open",
    tone: approval.value.state === "waiting" ? ("warning" as const) : approval.value.state === "blocked" ? ("critical" as const) : ("default" as const),
  },
])

const tabBadges = computed<Record<string, string>>(() => {
  const badges: Record<string, string> = {}
  if (candidate.value) {
    const summary = directiveCheckSummary(candidate.value)
    const openApproval = directiveApprovalState(candidate.value)
    badges.promotion = summary.failed
      ? `${summary.failed} failed`
      : openApproval.state === "waiting"
        ? `${openApproval.waiting} waiting`
        : "ready"
  }
  if (props.directive.versions.length > 1) badges.versions = String(props.directive.versions.length)
  if (props.directive.events.length) badges.audit = String(props.directive.events.length)
  return badges
})

function isTypingTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && Boolean(target.closest("input, textarea, select, [contenteditable]"))
}

function onGlobalKeydown(event: KeyboardEvent): void {
  if (event.metaKey || event.ctrlKey || event.altKey) return
  if (isTypingTarget(event.target)) return
  if (event.key === "[") {
    if (prevDirective.value) {
      event.preventDefault()
      goDirective(prevDirective.value.id)
    }
  } else if (event.key === "]") {
    if (nextDirective.value) {
      event.preventDefault()
      goDirective(nextDirective.value.id)
    }
  } else if (/^[1-6]$/.test(event.key)) {
    const target = DIRECTIVE_TABS[Number(event.key) - 1]
    if (target) {
      event.preventDefault()
      selectTab(target.id)
    }
  }
}

onMounted(() => window.addEventListener("keydown", onGlobalKeydown))
onBeforeUnmount(() => window.removeEventListener("keydown", onGlobalKeydown))

const about = ref<InstanceType<typeof GovernAboutPopover> | null>(null)

function copyText(value: string): void {
  if (import.meta.client) void navigator.clipboard.writeText(value)
}

function currentOrigin(): string {
  return import.meta.client ? window.location.origin : ""
}

const scopeLine = computed(
  () => `${props.directive.scope.org} · ${props.directive.scope.workspace} · ${props.directive.scope.area}`,
)
</script>

<template>
  <div class="mx-auto flex w-full max-w-[90rem] min-w-0 flex-1 flex-col pb-2">
    <header class="min-w-0">
      <div class="flex items-center justify-between gap-3">
        <NuxtLink
          :to="returnTo"
          class="inline-flex items-center gap-1.5 rounded text-xs text-fg-3 transition-colors hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        >
          <ChevronLeft :size="13" :stroke-width="1.9" aria-hidden="true" />
          Back to directives
        </NuxtLink>
        <div class="flex items-center gap-0.5">
          <button
            type="button"
            class="inline-flex size-7 items-center justify-center rounded-md text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 disabled:pointer-events-none disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            :disabled="!prevDirective"
            :aria-label="prevDirective ? `Previous directive: ${prevDirective.name}` : 'No previous directive'"
            @click="prevDirective && goDirective(prevDirective.id)"
          >
            <ChevronLeft :size="15" :stroke-width="1.9" aria-hidden="true" />
          </button>
          <button
            type="button"
            class="inline-flex size-7 items-center justify-center rounded-md text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 disabled:pointer-events-none disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            :disabled="!nextDirective"
            :aria-label="nextDirective ? `Next directive: ${nextDirective.name}` : 'No next directive'"
            @click="nextDirective && goDirective(nextDirective.id)"
          >
            <ChevronRight :size="15" :stroke-width="1.9" aria-hidden="true" />
          </button>
        </div>
      </div>

      <div class="mt-3.5 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
            <h1 class="ix-page-title text-fg-1 text-pretty">{{ directive.name }}</h1>
            <GovernLifecyclePill :state="primaryState" />
            <GovernCopyId :id="directive.id" label="Directive ID" truncate />
          </div>
          <p class="mt-1 line-clamp-2 max-w-[70ch] text-sm leading-5 text-fg-3" :title="directive.description">{{ directive.description }}</p>
          <p class="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs leading-4 text-fg-3">
            <span class="font-mono text-[0.6875rem]">{{ scopeLine }}</span>
            <span aria-hidden="true">·</span>
            <template v-if="live">
              <span>Live: <span class="font-mono text-fg-2">{{ live.version }}</span> since {{ formatGovernShortDate(live.liveFrom) }} by {{ live.author }}</span>
            </template>
            <template v-if="candidate">
              <span aria-hidden="true">·</span>
              <span>Candidate: <span class="font-mono text-fg-2">{{ candidate.version }}</span> by {{ candidate.author }}, {{ formatGovernRelative(candidate.createdAt) }}</span>
            </template>
            <template v-else>
              <span aria-hidden="true">·</span>
              <span>No candidate open</span>
            </template>
          </p>
          <p v-if="directive.agents.length" class="mt-2 flex flex-wrap items-center gap-1.5 text-xs leading-4 text-fg-3">
            <span>Used by</span>
            <NuxtLink
              v-for="agent in directive.agents"
              :key="agent.id"
              :to="`/agents/${agent.id}?tab=directives`"
              class="inline-flex h-6 items-center rounded-full border border-line-subtle bg-surface-1 px-2 text-[0.6875rem] text-fg-2 transition-colors hover:border-line hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            >{{ agent.name }}</NuxtLink>
          </p>
        </div>

        <div class="flex shrink-0 flex-wrap items-center gap-2">
          <GovernDataSourceChip :live="false" @open="about?.open()" />
          <GovernLockedAction
            :label="candidate ? `Approve ${candidate.version}` : 'New candidate'"
            :icon="candidate ? BadgeCheck : FileJson"
            variant="primary"
          />
          <GovernLockedAction
            v-if="candidate"
            :label="`Promote ${candidate.version}`"
            :icon="Upload"
            variant="secondary"
            size="sm"
          />
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <button
                type="button"
                class="inline-flex size-8 items-center justify-center rounded-md border border-line bg-surface-1 text-fg-2 transition-colors hover:border-line-strong hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                aria-label="More directive actions"
              >
                <Ellipsis :size="15" :stroke-width="1.9" aria-hidden="true" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" class="!w-64">
              <DropdownMenuLabel class="text-xs text-fg-3">Directive</DropdownMenuLabel>
              <DropdownMenuItem class="!text-xs" @select="copyText(directive.id)">
                <Copy :size="13" :stroke-width="1.9" aria-hidden="true" /> Copy ID
              </DropdownMenuItem>
              <DropdownMenuItem class="!text-xs" @select="copyText(`${currentOrigin()}/directives/${directive.id}`)">
                <ExternalLink :size="13" :stroke-width="1.9" aria-hidden="true" /> Copy link
              </DropdownMenuItem>
              <DropdownMenuItem class="!text-xs" @select="selectTab('diff')">
                <FileJson :size="13" :stroke-width="1.9" aria-hidden="true" /> Compare versions
              </DropdownMenuItem>
              <DropdownMenuItem class="!text-xs" @select="copyText(JSON.stringify(directive, null, 2))">
                <FileJson :size="13" :stroke-width="1.9" aria-hidden="true" /> Export JSON
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem class="!text-xs" disabled title="Read-only console. Requires a privileged write contract.">
                <MessageSquareWarning :size="13" :stroke-width="1.9" aria-hidden="true" /> Request changes
                <span class="ml-auto text-[0.625rem] text-fg-3">{{ candidate ? 'candidate' : 'no candidate' }}</span>
              </DropdownMenuItem>
              <DropdownMenuItem class="!text-xs" disabled title="Read-only console. Requires a privileged write contract.">
                <RotateCcw :size="13" :stroke-width="1.9" aria-hidden="true" /> Roll back
                <span class="ml-auto text-[0.625rem] text-fg-3">{{ candidate ? 'candidate open' : 'live version' }}</span>
              </DropdownMenuItem>
              <DropdownMenuItem class="!text-xs" disabled title="Read-only console. Requires a privileged write contract.">
                <FileJson :size="13" :stroke-width="1.9" aria-hidden="true" /> New draft
                <span class="ml-auto text-[0.625rem] text-fg-3">from {{ live?.version ?? 'scratch' }}</span>
              </DropdownMenuItem>
              <p class="border-t border-line-subtle px-2 py-2 text-[0.625rem] leading-3.5 text-fg-3">
                Read-only console. Requires a privileged write contract.
              </p>
            </DropdownMenuContent>
          </DropdownMenu>
          <GovernAboutPopover
            ref="about"
            :verdict="`${directives.length} directives · ${directive.versions.length} versions`"
            contract="operator.directives.versions.v1"
            :scope="scopeLine"
            :range="`${directive.versions.at(-1)?.version ?? '—'} → ${directive.versions[0]?.version ?? '—'}`"
            coverage="Preview fixtures · no directive read model connected"
            phase="D5 · Phase B2"
            :notes="[
              { lead: 'Directive, not policy.', body: 'A directive is instruction text with versions. A policy is a guardrail rule set published in immutable snapshots.' },
              { lead: 'Approvals exclude the author.', body: 'Any actor who wrote the candidate cannot approve it.' },
            ]"
          />
        </div>
      </div>
    </header>

    <div
      v-if="banner"
      class="mt-4 flex min-h-12 flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border px-4 py-2.5"
      :class="bannerTone[banner.tone]"
    >
      <p class="min-w-0 flex-1 text-[0.8125rem] leading-5">{{ banner.text }}</p>
      <button
        type="button"
        class="shrink-0 text-xs font-medium underline decoration-current underline-offset-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        @click="selectTab(banner.tab)"
      >
        {{ banner.action }}
      </button>
    </div>

    <div class="mt-4 grid grid-cols-2 gap-2 sm:gap-3 xl:grid-cols-4">
      <GovernStatTile
        v-for="kpi in kpis"
        :key="kpi.key"
        :label="kpi.label"
        :value="kpi.value"
        :helper="kpi.helper"
        :tone="kpi.tone"
        compact
      />
    </div>

    <div class="mt-5">
      <GovernTabBar
        :tabs="DIRECTIVE_TABS"
        :model-value="state.tab"
        :badges="tabBadges"
        aria-label="Directive views"
        @update:model-value="selectTab($event as DirectiveTab)"
      />
    </div>

    <div class="mt-5 min-w-0">
      <Transition name="govern-panel" mode="out-in">
        <div :key="state.tab" role="tabpanel" :aria-labelledby="`govern-tab-${state.tab}`" tabindex="0" class="min-w-0">
          <DirectiveOverviewTab v-if="state.tab === 'overview'" :directive="directive" @tab="selectTab" />
          <DirectiveVersionsTab
            v-else-if="state.tab === 'versions'"
            :directive="directive"
            @compare="(from, to) => update({ from, to, tab: 'diff' })"
            @audit="selectTab('audit')"
          />
          <DirectiveDiffTab v-else-if="state.tab === 'diff'" :directive="directive" :state="state" :defaults="defaults" @update="update" />
          <DirectivePromotionTab
            v-else-if="state.tab === 'promotion'"
            :directive="directive"
            @compare="(from, to) => update({ from, to, tab: 'diff' })"
            @audit="selectTab('audit')"
          />
          <DirectiveUsageTab v-else-if="state.tab === 'usage'" :directive="directive" />
          <DirectiveAuditTab v-else :directive="directive" />
        </div>
      </Transition>
    </div>

    <p class="mt-8 text-[0.6875rem] leading-4 text-fg-3">
      Read-only. Press 1–6 for tabs, [ and ] for the previous/next directive.
    </p>
  </div>
</template>

<style scoped>
.govern-panel-enter-active {
  transition: opacity 150ms ease, transform 150ms ease;
}
.govern-panel-leave-active {
  transition: opacity 100ms ease;
}
.govern-panel-enter-from {
  opacity: 0;
  transform: translateY(4px);
}
.govern-panel-leave-to {
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .govern-panel-enter-active,
  .govern-panel-leave-active {
    transition: none;
  }
}
</style>
