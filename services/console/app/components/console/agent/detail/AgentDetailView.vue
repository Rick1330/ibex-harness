<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import {
  Archive,
  ChevronLeft,
  ChevronRight,
  CirclePause,
  Copy,
  Ellipsis,
  ExternalLink,
  FileJson,
  Lock,
  Play,
  TriangleAlert,
  X,
} from "@lucide/vue"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import AgentHealthDot from "../primitives/AgentHealthDot.vue"
import AgentStatusPill from "../primitives/AgentStatusPill.vue"
import AgentEnvTag from "../primitives/AgentEnvTag.vue"
import AgentVersionTag from "../primitives/AgentVersionTag.vue"
import AgentCopyId from "../primitives/AgentCopyId.vue"
import GovernAboutPopover from "@/components/console/govern/primitives/GovernAboutPopover.vue"
import GovernDataSourceChip from "@/components/console/govern/primitives/GovernDataSourceChip.vue"
import AgentLockedAction from "../primitives/AgentLockedAction.vue"
import {
  AGENT_PERIOD_TITLE,
  agentHeadline,
  agentTabBadge,
  formatAgentCount,
  formatAgentDate,
  formatAgentMoney,
  formatAgentPercent,
  formatAgentRelative,
} from "@/lib/agent-detail"
import { AGENT_TABS, agentBudgetLeftPct, agentBudgetLeftUsd, agentProviderLabel, agentSummaries, type AgentDetail, type AgentTab } from "@/lib/agent-preview"
import BrandIcon from "@/components/console/BrandIcon.vue"
import AgentOverviewTab from "./tabs/AgentOverviewTab.vue"
import AgentRunsTab from "./tabs/AgentRunsTab.vue"
import AgentSessionsTab from "./tabs/AgentSessionsTab.vue"
import AgentDirectivesTab from "./tabs/AgentDirectivesTab.vue"
import AgentPoliciesTab from "./tabs/AgentPoliciesTab.vue"
import AgentMemoriesTab from "./tabs/AgentMemoriesTab.vue"
import AgentToolsTab from "./tabs/AgentToolsTab.vue"
import AgentCostTab from "./tabs/AgentCostTab.vue"
import AgentAuditTab from "./tabs/AgentAuditTab.vue"

const props = defineProps<{
  agent: AgentDetail
  returnTo: string
}>()

const route = useRoute()
const router = useRouter()

const VALID_TABS = AGENT_TABS.map((tab) => tab.id) as readonly string[]
function resolveTab(value: unknown): AgentTab {
  return typeof value === "string" && VALID_TABS.includes(value) ? (value as AgentTab) : "overview"
}

const tab = ref<AgentTab>(resolveTab(route.query.tab))
watch(
  () => route.query.tab,
  (value) => {
    tab.value = resolveTab(value)
  },
)

function selectTab(next: AgentTab, focus = false): void {
  tab.value = next
  const query = { ...route.query }
  if (next === "overview") delete query.tab
  else query.tab = next
  void router.replace({ query })
  if (focus) void nextTick(() => tablist.value?.querySelector<HTMLButtonElement>(`[data-agent-tab="${next}"]`)?.focus())
}

// Tab underline slides between tabs.
const tablist = ref<HTMLElement | null>(null)
const indicator = ref({ left: 0, width: 0, ready: false })
function moveIndicator(): void {
  const root = tablist.value
  if (!root) return
  const active = root.querySelector<HTMLButtonElement>(`[data-agent-tab="${tab.value}"]`)
  if (!active) return
  indicator.value = { left: active.offsetLeft, width: active.offsetWidth, ready: true }
}
watch(
  () => [tab.value, props.agent.id],
  () => void nextTick(moveIndicator),
  { immediate: true },
)
onMounted(() => void nextTick(moveIndicator))

// Prev/next agent through the same list order the /agents page uses.
const order = computed(() => agentSummaries)
const currentIndex = computed(() => order.value.findIndex((agent) => agent.id === props.agent.id))
const prevAgent = computed(() => (currentIndex.value > 0 ? order.value[currentIndex.value - 1]! : null))
const nextAgent = computed(() =>
  currentIndex.value >= 0 && currentIndex.value < order.value.length - 1 ? order.value[currentIndex.value + 1]! : null,
)

function goAgent(id: string): void {
  const query = route.query.return ? { return: route.query.return } : {}
  void router.push({ path: `/agents/${id}`, query })
}

// Sticky condensed header once the main header scrolls out.
const headerEl = ref<HTMLElement | null>(null)
const condensed = ref(false)
let observer: IntersectionObserver | null = null

function isTypingTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && Boolean(target.closest("input, textarea, select, [contenteditable]"))
}

function onGlobalKeydown(event: KeyboardEvent): void {
  if (event.metaKey || event.ctrlKey || event.altKey) return
  if (isTypingTarget(event.target)) return
  if (event.key === "[") {
    if (prevAgent.value) {
      event.preventDefault()
      goAgent(prevAgent.value.id)
    }
  } else if (event.key === "]") {
    if (nextAgent.value) {
      event.preventDefault()
      goAgent(nextAgent.value.id)
    }
  } else if (/^[1-9]$/.test(event.key)) {
    const target = AGENT_TABS[Number(event.key) - 1]
    if (target) {
      event.preventDefault()
      selectTab(target.id, true)
    }
  }
}

onMounted(() => {
  window.addEventListener("keydown", onGlobalKeydown)
  if (headerEl.value && typeof IntersectionObserver !== "undefined") {
    observer = new IntersectionObserver(
      ([entry]) => {
        condensed.value = !(entry?.isIntersecting ?? true)
      },
      { rootMargin: "-48px 0px 0px 0px" },
    )
    observer.observe(headerEl.value)
  }
})
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onGlobalKeydown)
  observer?.disconnect()
})

// Status banner: one at a time, priority order.
const banner = computed(() => {
  const agent = props.agent
  if (agent.status === "suspended") {
    return {
      tone: "border-transparent bg-transparent text-crit",
      icon: TriangleAlert,
      text: `Suspended by policy on ${formatAgentDate(agent.updatedAt)}: ${agent.suspendedReason ?? "no reason recorded"}.`,
      tab: "audit" as AgentTab,
      action: "View in Audit",
    }
  }
  if (agent.budget && agentBudgetLeftUsd(agent.budget) <= 0) {
    return {
      tone: "border-transparent bg-transparent text-crit",
      icon: TriangleAlert,
      text: "Spend budget exhausted. New runs are blocked until the period resets.",
      tab: "cost" as AgentTab,
      action: "Cost & budgets",
    }
  }
  if (agent.status === "draining") {
    return {
      tone: "border-transparent bg-transparent text-warn",
      icon: TriangleAlert,
      text: `Pausing: ${agent.stats.activeSessions} sessions still completing.`,
      tab: "sessions" as AgentTab,
      action: "Live sessions",
    }
  }
  if (agent.status === "paused") {
    return {
      tone: "border-line-subtle border-l-line-strong bg-raised text-fg-2",
      icon: CirclePause,
      text: `Paused. No new sessions start${agent.stats.activeSessions ? `; ${agent.stats.activeSessions} sessions still draining` : ""}.`,
      tab: "audit" as AgentTab,
      action: "View in Audit",
    }
  }
  if (agent.status === "archived") {
    return {
      tone: "border-dashed border-line-subtle border-l-line-strong bg-transparent text-fg-3",
      icon: Archive,
      text: "Archived. Read-only history.",
      tab: "audit" as AgentTab,
      action: "View in Audit",
    }
  }
  return null
})

const kpis = computed(() => {
  const agent = props.agent
  const stats = agent.stats
  return [
    {
      key: "last-run",
      label: "Last run",
      value:
        stats.lastRun === null
          ? "Never run"
          : stats.lastRun.status === "succeeded"
            ? "✓ Succeeded"
            : stats.lastRun.status === "failed"
              ? "✕ Failed"
              : stats.lastRun.status,
      sub: stats.lastRun ? formatAgentRelative(stats.lastRun.at) : "",
      tone: stats.lastRun?.status === "failed" ? "warn" : "default",
      tab: "runs" as AgentTab,
    },
    {
      key: "errors",
      label: "Error rate",
      value: stats.errorRate === null ? "Not reported yet" : formatAgentPercent(stats.errorRate),
      sub: stats.errorRate === null ? "" : `band ≤ ${formatAgentPercent(agent.errorBandPct)}`,
      tone: (stats.errorRate ?? 0) > agent.errorBandPct ? "warn" : "default",
      tab: "runs" as AgentTab,
    },
    {
      key: "p95",
      label: "p95 duration",
      value: stats.p95Ms === null ? "Not reported yet" : `${(stats.p95Ms / 1000).toFixed(1)}s`,
      sub: agent.latencyBudgetMs === null ? "" : `budget ${(agent.latencyBudgetMs / 1000).toFixed(1)}s`,
      tone: agent.latencyBudgetMs !== null && (stats.p95Ms ?? 0) > agent.latencyBudgetMs ? "warn" : "default",
      tab: "runs" as AgentTab,
    },
    {
      key: "budget",
      label: "Budget",
      value: agent.budget ? `${formatAgentMoney(agentBudgetLeftUsd(agent.budget))} left` : "No budget set",
      sub: agent.budget
        ? `${formatAgentPercent(agentBudgetLeftPct(agent.budget))} of ${formatAgentMoney(agent.budget.totalUsd)}`
        : "",
      tone: agent.budget
        ? agentBudgetLeftUsd(agent.budget) <= 0
          ? "crit"
          : agentBudgetLeftPct(agent.budget) < agent.budget.floorPct
            ? "warn"
            : "default"
        : "default",
      tab: "cost" as AgentTab,
    },
    {
      key: "sessions",
      label: "Sessions",
      value: `${formatAgentCount(stats.sessions)}${stats.activeSessions ? ` · ${stats.activeSessions} live` : ""}`,
      sub: "",
      tone: "default",
      tab: "sessions" as AgentTab,
    },
    {
      key: "memories",
      label: "Memories",
      value: formatAgentCount(stats.memories),
      sub: stats.quarantined ? `${stats.quarantined} quarantined` : "",
      tone: stats.quarantined ? "warn" : "default",
      tab: "memories" as AgentTab,
    },
  ]
})

function copyText(value: string): void {
  if (import.meta.client) void navigator.clipboard.writeText(value)
}

function currentOrigin(): string {
  return import.meta.client ? window.location.origin : ""
}

const about = ref<InstanceType<typeof GovernAboutPopover> | null>(null)

// Archive and Delete never write. They open a cascade preview so an operator can
// see exactly what a privileged write contract would affect.
const cascade = ref<"archive" | "delete" | null>(null)
const cascadeDialog = ref<HTMLDialogElement | null>(null)

const cascadeRows = computed(() => {
  if (!cascade.value) return []
  const agent = props.agent
  const stats = agent.stats
  const rows = [
    { label: "Sessions", value: `${formatAgentCount(stats.sessions)}${stats.activeSessions ? ` · ${stats.activeSessions} live` : ""}` },
    { label: "Memories", value: `${formatAgentCount(stats.memories)}${stats.quarantined ? ` · ${stats.quarantined} quarantined` : ""}` },
    { label: "Runs", value: formatAgentCount(stats.runs) },
    { label: "Directives", value: agent.directive ? `v${agent.directive.version} detached` : "None attached" },
    { label: "Policies", value: agent.policy ? `v${agent.policy.version} detached` : "None attached" },
  ]
  if (cascade.value === "archive") {
    rows.push({ label: "Audit history", value: "Retained" })
  } else {
    rows.push({ label: "Audit history", value: "Retained per organization policy" })
  }
  return rows
})

const cascadeCopy = computed(() => {
  if (cascade.value === "archive") {
    return {
      title: `Archive ${props.agent.name}`,
      summary: "The agent stops starting sessions and leaves the active inventory. History stays readable.",
      confirm: "Archive agent",
    }
  }
  if (cascade.value === "delete") {
    return {
      title: `Delete ${props.agent.name}`,
      summary: "The agent, its configuration and its memory records are removed. This cannot be undone.",
      confirm: "Delete agent",
    }
  }
  return null
})

function openCascade(kind: "archive" | "delete"): void {
  cascade.value = kind
  void nextTick(() => cascadeDialog.value?.showModal())
}

function closeCascade(): void {
  cascadeDialog.value?.close()
  cascade.value = null
}

</script>

<template>
  <div class="mx-auto flex w-full max-w-[90rem] min-w-0 flex-1 flex-col pb-2">
    <div ref="headerEl">
      <header class="min-w-0">
        <div class="flex items-center justify-between gap-3">
          <NuxtLink :to="returnTo" class="inline-flex items-center gap-1.5 rounded text-xs text-fg-3 transition-colors hover:text-fg-1">
            <ChevronLeft :size="13" :stroke-width="1.9" aria-hidden="true" />
            Back to agents
          </NuxtLink>
          <div class="flex items-center gap-0.5">
            <button
              type="button"
              class="inline-flex size-7 items-center justify-center rounded-md text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 disabled:pointer-events-none disabled:opacity-40"
              :disabled="!prevAgent"
              :aria-label="prevAgent ? `Previous agent: ${prevAgent.name}` : 'No previous agent'"
              @click="prevAgent && goAgent(prevAgent.id)"
            >
              <ChevronLeft :size="15" :stroke-width="1.9" aria-hidden="true" />
            </button>
            <button
              type="button"
              class="inline-flex size-7 items-center justify-center rounded-md text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 disabled:pointer-events-none disabled:opacity-40"
              :disabled="!nextAgent"
              :aria-label="nextAgent ? `Next agent: ${nextAgent.name}` : 'No next agent'"
              @click="nextAgent && goAgent(nextAgent.id)"
            >
              <ChevronRight :size="15" :stroke-width="1.9" aria-hidden="true" />
            </button>
          </div>
        </div>

        <div class="mt-3.5 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
              <h1 class="ix-page-title text-fg-1 text-pretty">{{ agent.name }}</h1>
              <AgentHealthDot :health="agent.health" :reasons="agent.healthReasons" />
              <AgentStatusPill :status="agent.status" :draining-count="agent.stats.activeSessions" />
              <AgentCopyId :id="agent.id" label="Agent ID" truncate />
            </div>
            <p class="mt-1 line-clamp-2 max-w-[70ch] text-sm leading-5 text-fg-3 sm:line-clamp-1" :title="agent.description">
              {{ agent.description }}
            </p>
            <p class="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs leading-4 text-fg-3">
              <AgentVersionTag label="Agent" :value="`v${agent.agentVersion}`" />
              <span aria-hidden="true">·</span>
              <span class="inline-flex items-center gap-1.5 font-mono text-[0.6875rem]">
                <BrandIcon :id="agent.provider" :size="13" :label="`${agentProviderLabel(agent.provider)} logo`" />
                {{ agent.model }} · {{ agentProviderLabel(agent.provider) }}
              </span>
              <template v-if="agent.directive">
                <span aria-hidden="true">·</span>
                <button type="button" class="inline-flex items-center gap-1 underline decoration-line-strong underline-offset-3 hover:text-fg-1" @click="selectTab('directives')">
                  <AgentVersionTag label="Directive" :value="`v${agent.directive.version}`" tone="default" />
                </button>
              </template>
              <template v-if="agent.policy">
                <span aria-hidden="true">·</span>
                <button type="button" class="inline-flex items-center gap-1 underline decoration-line-strong underline-offset-3 hover:text-fg-1" @click="selectTab('policies')">
                  <AgentVersionTag label="Policy" :value="`v${agent.policy.version}`" tone="default" />
                </button>
              </template>
              <span aria-hidden="true">·</span>
              <AgentEnvTag :env="agent.env" />
              <span aria-hidden="true">·</span>
              <span>{{ agent.owner }}</span>
              <span aria-hidden="true">·</span>
              <span :title="`Created by ${agent.createdBy}`">Created {{ formatAgentDate(agent.createdAt) }}</span>
              <span v-for="tag in agent.tags.slice(0, 3)" :key="tag" class="rounded-full border border-line-subtle px-1.5 py-px text-[0.625rem] text-fg-3">{{ tag }}</span>
              <span v-if="agent.tags.length > 3" class="text-[0.625rem] text-fg-3">+{{ agent.tags.length - 3 }}</span>
            </p>
          </div>

          <div class="flex shrink-0 flex-wrap items-center gap-2">
            <GovernDataSourceChip state="illustrative" @open="about?.open()" />
            <AgentLockedAction
              :label="agent.status === 'paused' ? 'Activate' : 'Pause'"
              :icon="agent.status === 'paused' ? Play : CirclePause"
              variant="primary"
              size="sm"
            />
            <DropdownMenu>
              <DropdownMenuTrigger as-child>
                <button
                  type="button"
                  class="inline-flex size-8 items-center justify-center rounded-md border border-line bg-surface-1 text-fg-2 transition-colors hover:border-line-strong hover:text-fg-1"
                  aria-label="More agent actions"
                >
                  <Ellipsis :size="15" :stroke-width="1.9" aria-hidden="true" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" class="!w-60">
                <DropdownMenuLabel class="text-xs text-fg-3">Agent</DropdownMenuLabel>
                <DropdownMenuItem class="!text-xs" @select="copyText(agent.id)">
                  <Copy :size="13" :stroke-width="1.9" aria-hidden="true" /> Copy ID
                </DropdownMenuItem>
                <DropdownMenuItem class="!text-xs" @select="copyText(`${currentOrigin()}/agents/${agent.id}`)">
                  <ExternalLink :size="13" :stroke-width="1.9" aria-hidden="true" /> Copy link
                </DropdownMenuItem>
                <DropdownMenuItem class="!text-xs" as-child>
                  <NuxtLink to="/explore" @click.stop>
                    <FileJson :size="13" :stroke-width="1.9" aria-hidden="true" /> Open in Explore
                  </NuxtLink>
                </DropdownMenuItem>
                <DropdownMenuItem class="!text-xs" @select="copyText(JSON.stringify(agent.raw, null, 2))">
                  <FileJson :size="13" :stroke-width="1.9" aria-hidden="true" /> Export JSON
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  class="!text-xs"
                  title="Read-only console. Requires a privileged write contract."
                  @select="openCascade('archive')"
                >
                  <Lock :size="13" :stroke-width="1.9" aria-hidden="true" /> Archive
                  <span class="ml-auto text-[0.625rem] text-fg-3">{{ agent.stats.sessions }} sessions · {{ agent.stats.memories }} memories</span>
                </DropdownMenuItem>
                <DropdownMenuItem
                  class="!text-xs !text-crit/70"
                  title="Read-only console. Requires a privileged write contract."
                  @select="openCascade('delete')"
                >
                  <Lock :size="13" :stroke-width="1.9" aria-hidden="true" /> Delete
                  <span class="ml-auto text-[0.625rem] text-fg-3">follows retention policy</span>
                </DropdownMenuItem>
                <p class="border-t border-line-subtle px-2 py-2 text-[0.625rem] leading-3.5 text-fg-3">
                  Read-only console. Requires a privileged write contract. The counts preview the archive cascade.
                </p>
              </DropdownMenuContent>
            </DropdownMenu>
            <GovernAboutPopover
              ref="about"
              state="illustrative"
              :verdict="`This page renders a recorded design fixture for ${agent.name}. Agent summary, detail, health, and statistics contracts are not connected, so no row here is live organization inventory.`"
              contract="operator.agents.detail.v1 [NEEDS-BACKEND]"
              :scope="`org_demo_42 · ${agent.env}`"
              range="Last 14 days · fixture clock"
              coverage="0% live · illustrative agent"
              :notes="[
                { lead: 'Versions are labels, not history.', body: 'Agent, directive, and policy versions are recorded on the fixture so the relationship is visible. A version history contract is not connected.' },
                { lead: 'Missing series stay missing.', body: 'Run-volume, spend-over-time, and drift charts need GET /v1/agents/{id}/stats, so they show Not reported yet instead of a fabricated line.' },
                { lead: 'Health is derived once.', body: 'The same function drives the list and this page, so a suspended agent is not healthy here and failing there.' },
              ]"
            />
          </div>
        </div>
      </header>

      <div v-if="banner" class="mt-4 flex min-h-12 flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border px-4 py-2.5" :class="banner.tone">
        <component :is="banner.icon" :size="14" :stroke-width="1.9" class="shrink-0" aria-hidden="true" />
        <p class="min-w-0 flex-1 text-[0.8125rem] leading-5">{{ banner.text }}</p>
        <button type="button" class="shrink-0 text-xs font-medium underline decoration-current underline-offset-3" @click="selectTab(banner.tab)">
          {{ banner.action }}
        </button>
      </div>

      <div class="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-3 xl:grid-cols-6">
        <button
          v-for="kpi in kpis"
          :key="kpi.key"
          type="button"
          class="flex min-w-0 flex-col items-start gap-0.5 rounded-lg border px-4 py-3 text-left transition-colors hover:border-line"
          :class="
            kpi.tone === 'crit'
              ? 'border-crit/30 bg-crit-tint/30'
              : kpi.tone === 'warn'
                ? 'border-warn/30 bg-warn-tint/30'
                : 'border-line-subtle bg-surface-1'
          "
          @click="selectTab(kpi.tab)"
        >
          <span class="text-xs leading-4 text-fg-3">{{ kpi.label }}</span>
          <span
            class="w-full truncate font-mono text-lg leading-6 font-semibold tabular-nums"
            :class="kpi.tone === 'crit' ? 'text-crit' : kpi.tone === 'warn' ? 'text-warn' : 'text-fg-1'"
          >
            {{ kpi.value }}
          </span>
          <span v-if="kpi.sub" class="w-full truncate text-xs leading-4 text-fg-3">{{ kpi.sub }}</span>
        </button>
      </div>
    </div>

    <div class="sticky top-12 z-20 -mx-4 mt-6 border-b border-line-subtle bg-canvas/85 backdrop-blur-sm sm:-mx-5 lg:-mx-6">
      <div class="mx-auto flex h-12 max-w-[90rem] items-center gap-3 px-4 sm:px-5 lg:px-6">
        <div
          v-show="condensed"
          class="hidden min-w-0 shrink-0 items-center gap-2 max-lg:hidden"
        >
          <span class="max-w-[22ch] truncate text-xs font-medium text-fg-2">{{ agent.name }}</span>
          <AgentHealthDot :health="agent.health" dot-only size="sm" />
          <span class="h-4 w-px bg-line-subtle" aria-hidden="true" />
        </div>

        <div ref="tablist" class="relative flex min-w-0 flex-1 gap-1 overflow-x-auto" style="scrollbar-width: none" role="tablist" aria-label="Agent views">
          <button
            v-for="entry in AGENT_TABS"
            :id="`agent-tab-${entry.id}`"
            :key="entry.id"
            type="button"
            role="tab"
            class="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-md px-2.5 text-sm font-medium transition-colors"
            :class="tab === entry.id ? 'text-fg-1' : 'text-fg-3 hover:text-fg-1'"
            :data-agent-tab="entry.id"
            :aria-selected="tab === entry.id"
            :aria-controls="`agent-panel-${entry.id}`"
            :tabindex="tab === entry.id ? 0 : -1"
            @click="selectTab(entry.id)"
            @keydown.left.prevent="selectTab(AGENT_TABS[(AGENT_TABS.findIndex((candidate) => candidate.id === tab) + AGENT_TABS.length - 1) % AGENT_TABS.length]!.id, true)"
            @keydown.right.prevent="selectTab(AGENT_TABS[(AGENT_TABS.findIndex((candidate) => candidate.id === tab) + 1) % AGENT_TABS.length]!.id, true)"
          >
            {{ entry.label }}
            <span
              v-if="agentTabBadge(agent, entry.id)"
              class="inline-flex h-4.5 items-center gap-1 rounded-full px-1.5 font-mono text-[0.625rem] leading-none"
              :class="agentTabBadge(agent, entry.id)!.tone === 'warning' ? 'bg-warn-tint text-warn' : agentTabBadge(agent, entry.id)!.tone === 'destructive' ? 'bg-crit-tint text-crit' : 'bg-surface-2 text-fg-3'"
            >
              {{ agentTabBadge(agent, entry.id)!.label }}
            </span>
          </button>
          <span
            class="absolute bottom-0 left-0 h-0.5 rounded bg-accent-memory"
            :class="indicator.ready && 'transition-[transform,width] duration-150 ease-out'"
            :style="{ transform: `translateX(${indicator.left}px)`, width: `${indicator.width}px` }"
            aria-hidden="true"
          />
        </div>
      </div>
    </div>

    <div class="mt-6 min-w-0">
      <p class="mb-4 line-clamp-1 text-base leading-6 font-medium text-fg-1" :title="agentHeadline(agent, tab)">
        {{ agentHeadline(agent, tab) }}
      </p>
      <Transition name="agent-panel" mode="out-in">
        <div :id="`agent-panel-${tab}`" :key="tab" class="min-w-0" role="tabpanel" :aria-labelledby="`agent-tab-${tab}`" tabindex="0">
          <AgentOverviewTab v-if="tab === 'overview'" :agent="agent" @tab="selectTab" />
          <AgentRunsTab v-else-if="tab === 'runs'" :agent="agent" />
          <AgentSessionsTab v-else-if="tab === 'sessions'" :agent="agent" />
          <AgentDirectivesTab v-else-if="tab === 'directives'" :agent="agent" />
          <AgentPoliciesTab v-else-if="tab === 'policies'" :agent="agent" />
          <AgentMemoriesTab v-else-if="tab === 'memories'" :agent="agent" :return-to="returnTo" />
          <AgentToolsTab v-else-if="tab === 'tools'" :agent="agent" />
          <AgentCostTab v-else-if="tab === 'cost'" :agent="agent" />
          <AgentAuditTab v-else :agent="agent" />
        </div>
      </Transition>
    </div>

    <p class="mt-8 text-[0.6875rem] leading-4 text-fg-3">
      Period: {{ AGENT_PERIOD_TITLE }}. Press 1–9 for tabs, [ and ] for the previous/next agent.
    </p>

    <dialog
      ref="cascadeDialog"
      class="m-auto w-[min(30rem,calc(100vw-1.5rem))] max-h-[calc(100dvh-2rem)] max-w-none overflow-y-auto rounded-lg border border-line bg-overlay p-0 text-fg-1 shadow-2xl backdrop:bg-canvas/70"
      :aria-labelledby="`agent-cascade-title`"
      @close="cascade = null"
      @click="($event.target === cascadeDialog) && closeCascade()"
    >
      <template v-if="cascadeCopy">
        <div class="flex items-start justify-between gap-3 border-b border-line-subtle px-4 py-3">
          <div class="min-w-0">
            <h2 id="agent-cascade-title" class="flex items-center gap-2 text-sm font-semibold text-fg-1">
              <Lock :size="13" :stroke-width="1.9" class="text-fg-3" aria-hidden="true" />
              {{ cascadeCopy.title }}
            </h2>
            <p class="mt-1 text-xs leading-5 text-fg-3">{{ cascadeCopy.summary }}</p>
          </div>
          <button
            type="button"
            class="inline-flex size-7 shrink-0 items-center justify-center rounded-md text-fg-3 hover:bg-surface-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            aria-label="Close cascade preview"
            @click="closeCascade"
          >
            <X :size="15" :stroke-width="1.8" aria-hidden="true" />
          </button>
        </div>
        <div class="px-4 py-3">
          <p class="text-[0.6875rem] font-medium tracking-[0.06em] text-fg-3 uppercase">What this would affect</p>
          <dl class="mt-2 divide-y divide-line-subtle rounded-lg border border-line-subtle">
            <div v-for="row in cascadeRows" :key="row.label" class="flex items-center justify-between gap-3 px-3 py-2 text-xs">
              <dt class="text-fg-3">{{ row.label }}</dt>
              <dd class="truncate font-mono text-fg-2 tabular-nums">{{ row.value }}</dd>
            </div>
          </dl>
          <p v-if="agent.stats.activeSessions" class="mt-2 text-[0.6875rem] leading-4 text-warn">
            {{ agent.stats.activeSessions }} live {{ agent.stats.activeSessions === 1 ? "session must" : "sessions must" }} finish or be terminated before a write can complete.
          </p>
        </div>
        <div class="flex items-center justify-between gap-3 border-t border-line-subtle px-4 py-3">
          <p class="min-w-0 text-[0.6875rem] leading-4 text-fg-3">
            Read-only console. Requires a privileged write contract.
          </p>
          <div class="flex shrink-0 items-center gap-2">
            <button type="button" class="ix-button-secondary h-8 text-xs" @click="closeCascade">Cancel</button>
            <button
              type="button"
              class="ix-button-secondary h-8 gap-1.5 text-xs"
              :class="cascade === 'delete' ? '!border-crit/40 !text-crit/70' : ''"
              disabled
              title="Read-only console. Requires a privileged write contract."
            >
              <Lock :size="11" :stroke-width="1.9" aria-hidden="true" />
              {{ cascadeCopy.confirm }}
            </button>
          </div>
        </div>
      </template>
    </dialog>
  </div>
</template>

<style scoped>
.agent-panel-enter-active {
  transition: opacity 150ms ease, transform 150ms ease;
}

.agent-panel-leave-active {
  transition: opacity 100ms ease;
}

.agent-panel-enter-from {
  opacity: 0;
  transform: translateY(4px);
}

.agent-panel-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .agent-panel-enter-active,
  .agent-panel-leave-active {
    transition: none;
  }
}
</style>
