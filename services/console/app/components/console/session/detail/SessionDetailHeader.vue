<script setup lang="ts">
import { computed, ref } from "vue"
import {
  ArrowLeft,
  ArrowUpRight,
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  Ellipsis,
  FileJson,
  Info,
  Link2,
  Lock,
  TriangleAlert,
} from "@lucide/vue"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { PreviewSession } from "@/lib/session-preview"
import { formatSessionStart } from "@/lib/session-detail"
import MemoryAgentBadge from "@/components/console/memory/list/primitives/MemoryAgentBadge.vue"
import GovernAboutPopover from "@/components/console/govern/primitives/GovernAboutPopover.vue"
import GovernDataSourceChip from "@/components/console/govern/primitives/GovernDataSourceChip.vue"

const props = defineProps<{
  session: PreviewSession
  returnTo: string
  prevId: string | null
  nextId: string | null
  driftCount: number
  failureCount: number
  copiedId: boolean
}>()

const emit = defineEmits<{
  copy: [value: string, label: string]
  "show-raw-json": []
  "jump-drift": []
}>()

const completed = computed(() => props.failureCount === 0)
const about = ref<InstanceType<typeof GovernAboutPopover> | null>(null)

function openAbout(): void {
  about.value?.open()
}

function copyLink(): void {
  if (!import.meta.client) return
  emit("copy", window.location.href, "Session link")
}
</script>

<template>
  <header class="min-w-0">
    <div class="flex items-center justify-between gap-3">
      <NuxtLink
        :to="returnTo"
        class="inline-flex items-center gap-1.5 rounded text-xs text-fg-3 transition-colors hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
      >
        <ArrowLeft :size="13" :stroke-width="1.75" aria-hidden="true" />
        Sessions
      </NuxtLink>

      <nav class="flex items-center gap-0.5" aria-label="Sessions">
        <Tooltip :delay-duration="200">
          <TooltipTrigger as-child>
            <NuxtLink
              v-if="prevId"
              :to="prevId ? `/sessions/${encodeURIComponent(prevId)}?return=${encodeURIComponent(returnTo)}` : returnTo"
              class="inline-flex size-7 items-center justify-center rounded-md text-fg-3 transition-colors hover:bg-raised hover:text-fg-1"
              :aria-label="`Previous session ${prevId}`"
            >
              <ChevronLeft :size="15" :stroke-width="1.75" aria-hidden="true" />
            </NuxtLink>
            <span
              v-else
              role="link"
              aria-disabled="true"
              class="inline-flex size-7 items-center justify-center rounded-md text-fg-off opacity-40"
              aria-label="No previous session"
            >
              <ChevronLeft :size="15" :stroke-width="1.75" aria-hidden="true" />
            </span>
          </TooltipTrigger>
          <TooltipContent side="bottom" :side-offset="4" class="!text-xs">Previous session</TooltipContent>
        </Tooltip>
        <Tooltip :delay-duration="200">
          <TooltipTrigger as-child>
            <NuxtLink
              v-if="nextId"
              :to="nextId ? `/sessions/${encodeURIComponent(nextId)}?return=${encodeURIComponent(returnTo)}` : returnTo"
              class="inline-flex size-7 items-center justify-center rounded-md text-fg-3 transition-colors hover:bg-raised hover:text-fg-1"
              :aria-label="`Next session ${nextId}`"
            >
              <ChevronRight :size="15" :stroke-width="1.75" aria-hidden="true" />
            </NuxtLink>
            <span
              v-else
              role="link"
              aria-disabled="true"
              class="inline-flex size-7 items-center justify-center rounded-md text-fg-off opacity-40"
              aria-label="No next session"
            >
              <ChevronRight :size="15" :stroke-width="1.75" aria-hidden="true" />
            </span>
          </TooltipTrigger>
          <TooltipContent side="bottom" :side-offset="4" class="!text-xs">Next session</TooltipContent>
        </Tooltip>
      </nav>
    </div>

    <div class="mt-1.5 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between sm:gap-x-4">
      <div class="min-w-0 flex-1">
        <div class="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1.5">
          <h1 class="min-w-0 ix-page-title text-fg-1 text-pretty">{{ session.title }}</h1>
          <span
            v-if="completed"
            class="inline-flex h-5.5 items-center gap-1.5 rounded-full border border-transparent bg-transparent px-2 text-xs leading-none font-medium whitespace-nowrap text-ok"
          >
            <Check :size="11" :stroke-width="2.2" aria-hidden="true" />
            Completed
          </span>
          <span
            v-else
            class="inline-flex h-5.5 items-center gap-1.5 rounded-full border border-transparent bg-transparent px-2 text-xs leading-none font-medium whitespace-nowrap text-crit"
          >
            <TriangleAlert :size="11" :stroke-width="2" aria-hidden="true" />
            {{ failureCount }} failed
          </span>
          <button
            v-if="driftCount > 0"
            type="button"
            class="inline-flex h-5.5 items-center gap-1.5 rounded-full border border-transparent bg-transparent px-2 text-xs leading-none font-medium whitespace-nowrap text-warn transition-colors hover:border-warn/55 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            @click="emit('jump-drift')"
          >
            <TriangleAlert :size="11" :stroke-width="2" aria-hidden="true" />
            {{ driftCount }} drift {{ driftCount === 1 ? "advisory" : "advisories" }}
          </button>
        </div>

        <div class="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs leading-4 text-fg-3">
          <MemoryAgentBadge :name="session.agent" :agent-id="session.agent" />
          <span class="hidden text-fg-off sm:inline" aria-hidden="true">·</span>
          <span class="inline-flex items-center gap-1.5 whitespace-nowrap">
            <span
              class="size-1.5 rounded-full"
              :class="session.env === 'production' ? 'bg-ok' : session.env === 'staging' ? 'bg-warn' : 'bg-fg-off'"
              aria-hidden="true"
            />
            {{ session.env }}
          </span>
          <span class="hidden text-fg-off sm:inline" aria-hidden="true">·</span>
          <span class="group/copy inline-flex min-w-0 items-center gap-1">
            <span class="truncate font-mono text-fg-2">{{ session.id }}</span>
            <Tooltip :delay-duration="200">
              <TooltipTrigger as-child>
                <button
                  type="button"
                  class="inline-flex size-5 items-center justify-center rounded text-fg-3 opacity-60 transition-[opacity,color,background-color] hover:bg-raised hover:text-fg-1 group-hover/copy:opacity-100 focus-visible:opacity-100"
                  :aria-label="copiedId ? 'Session ID copied' : `Copy session ID ${session.id}`"
                  @click="emit('copy', session.id, 'Session ID')"
                >
                  <Check v-if="copiedId" :size="11" :stroke-width="2" class="text-ok" aria-hidden="true" />
                  <Copy v-else :size="11" :stroke-width="1.75" aria-hidden="true" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom" :side-offset="4" class="!text-xs">
                {{ copiedId ? `Copied ${session.id}` : "Copy session ID" }}
              </TooltipContent>
            </Tooltip>
          </span>
          <span class="hidden text-fg-off sm:inline" aria-hidden="true">·</span>
          <span class="whitespace-nowrap font-mono tabular-nums">{{ formatSessionStart(session) }}</span>
          <span class="hidden text-fg-off sm:inline" aria-hidden="true">·</span>
          <span class="whitespace-nowrap">{{ session.turns }} turns</span>
        </div>
      </div>

      <div class="flex shrink-0 items-center gap-1.5 max-sm:w-full max-sm:justify-end">
        <GovernDataSourceChip state="illustrative" @open="about?.open()" />
        <GovernAboutPopover
          ref="about"
          state="illustrative"
          verdict="This session is a recorded design fixture. Session title, turns, trace spans, evidence coverage, and cost are illustrative; no live session or tenant content was observed."
          contract="operator.sessions.detail.v1 + trace joins [NEEDS-BACKEND]"
          :scope="`org_demo_42 · ${session.env}`"
          :range="`Session ${session.id} · fixture clock`"
          coverage="0% live · illustrative session"
          :notes="[
            { lead: 'Illustrative timing.', body: 'Span offsets show execution order, not measured production latency.' },
            { lead: 'Cost and tokens are fixture values.', body: 'They are internally consistent with the recorded session, but they are not an invoice or a billing claim.' },
            { lead: 'Read-only.', body: 'Annotate, share, and replay require a privileged write contract.' },
          ]"
        />

        <NuxtLink
          to="/explore"
          class="ix-button-secondary h-8 gap-1.5 px-2.5 text-xs"
          aria-label="Open this session in traces"
        >
          Open in traces
          <ArrowUpRight :size="12" :stroke-width="1.75" aria-hidden="true" />
        </NuxtLink>

        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <button
              type="button"
              class="inline-flex size-8 items-center justify-center rounded-md border border-line bg-surface text-fg-2 transition-colors hover:border-line-strong hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
              aria-label="More session actions"
            >
              <Ellipsis :size="15" :stroke-width="1.75" aria-hidden="true" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" class="!w-60">
            <DropdownMenuLabel class="text-xs text-fg-3">Session</DropdownMenuLabel>
            <DropdownMenuItem value="contract" class="!text-xs" @select="openAbout">
              <Info :size="13" :stroke-width="1.75" aria-hidden="true" />
              About this data
            </DropdownMenuItem>
            <DropdownMenuItem value="raw" class="!text-xs" @select="emit('show-raw-json')">
              <FileJson :size="13" :stroke-width="1.75" aria-hidden="true" />
              View raw JSON
            </DropdownMenuItem>
            <DropdownMenuItem value="link" class="!text-xs" @select="copyLink">
              <Link2 :size="13" :stroke-width="1.75" aria-hidden="true" />
              Copy link
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem value="annotate" disabled class="!text-xs" title="Read-only console. Requires a privileged write contract.">
              <Lock :size="13" :stroke-width="1.75" aria-hidden="true" />
              Annotate turn
            </DropdownMenuItem>
            <DropdownMenuItem value="share" disabled class="!text-xs" title="Read-only console. Requires a privileged write contract.">
              <Lock :size="13" :stroke-width="1.75" aria-hidden="true" />
              Share session
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  </header>
</template>

<style scoped>
</style>
