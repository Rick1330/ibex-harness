<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue"
import {
  Activity,
  ArrowLeft,
  ArrowUpRight,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Copy,
  Check,
  Ellipsis,
  FileClock,
  FileJson,
  ListOrdered,
  Lock,
  ThumbsUp,
} from "@lucide/vue"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { MEMORY_CATEGORY_LABELS, memoryRelativeTime, type MemoryCategory } from "@/lib/memory-preview"
import type { MemoryDetail } from "@/lib/memory-detail-preview"
import MemoryStatusPill from "./primitives/MemoryStatusPill.vue"
import MemoryStatTile from "./primitives/MemoryStatTile.vue"
import MemoryScoreBar from "./primitives/MemoryScoreBar.vue"
import MemoryEmptyValue from "./primitives/MemoryEmptyValue.vue"
import GovernAboutPopover from "@/components/console/govern/primitives/GovernAboutPopover.vue"
import GovernDataSourceChip from "@/components/console/govern/primitives/GovernDataSourceChip.vue"

const props = defineProps<{
  detail: MemoryDetail
  memoryId: string
  returnTo: string
  prevTarget: string | null
  nextTarget: string | null
}>()

const emit = defineEmits<{ navigate: [id: string]; "show-raw-json": [] }>()

const about = ref<InstanceType<typeof GovernAboutPopover> | null>(null)

const CATEGORY_ICONS: Record<MemoryCategory, typeof BookOpen> = {
  preference: ThumbsUp,
  factual: BookOpen,
  behavioral: Activity,
  episodic: FileClock,
  procedural: ListOrdered,
}

const memory = computed(() => props.detail.memory)
const categoryLabel = computed(() => MEMORY_CATEGORY_LABELS[memory.value.category])
const categoryIcon = computed(() => CATEGORY_ICONS[memory.value.category])
const sourceSession = computed(() =>
  memory.value.sessionId ? `/sessions/${encodeURIComponent(memory.value.sessionId)}` : null,
)
const linkedSessions = computed(() => props.detail.retrieval.sessions)
const includedCount = computed(() => linkedSessions.value.filter((session) => session.usage === "injected").length)

const copied = ref(false)
let copyTimer: ReturnType<typeof setTimeout> | null = null

async function copyId(): Promise<void> {
  try {
    await navigator.clipboard.writeText(memory.value.id)
    copied.value = true
  } catch {
    copied.value = false
  }
  if (copyTimer) clearTimeout(copyTimer)
  copyTimer = setTimeout(() => {
    copied.value = false
  }, 1_500)
}

onBeforeUnmount(() => {
  if (copyTimer) clearTimeout(copyTimer)
})
</script>

<template>
  <header class="min-w-0">
    <div class="flex items-center justify-between gap-3">
      <NuxtLink
        :to="returnTo"
        class="inline-flex items-center gap-1.5 rounded text-xs text-fg-3 transition-colors hover:text-fg-1"
      >
        <ArrowLeft :size="13" :stroke-width="1.75" aria-hidden="true" />
        {{ returnTo.startsWith("/sessions/") ? "Back to session" : "Back to memories" }}
      </NuxtLink>

      <div class="flex items-center gap-0.5">
        <Tooltip :delay-duration="200">
          <TooltipTrigger as-child>
            <button
              type="button"
              class="inline-flex size-7 items-center justify-center rounded-md text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 disabled:pointer-events-none disabled:opacity-40"
              :disabled="!prevTarget"
              :aria-label="prevTarget ? `Previous memory ${prevTarget}` : 'No previous memory'"
              @click="prevTarget && emit('navigate', prevTarget)"
            >
              <ChevronLeft :size="15" :stroke-width="1.75" aria-hidden="true" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="bottom" :side-offset="4" class="!text-xs">Previous memory (K)</TooltipContent>
        </Tooltip>
        <Tooltip :delay-duration="200">
          <TooltipTrigger as-child>
            <button
              type="button"
              class="inline-flex size-7 items-center justify-center rounded-md text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 disabled:pointer-events-none disabled:opacity-40"
              :disabled="!nextTarget"
              :aria-label="nextTarget ? `Next memory ${nextTarget}` : 'No next memory'"
              @click="nextTarget && emit('navigate', nextTarget)"
            >
              <ChevronRight :size="15" :stroke-width="1.75" aria-hidden="true" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="bottom" :side-offset="4" class="!text-xs">Next memory (J)</TooltipContent>
        </Tooltip>
      </div>
    </div>

    <div class="mt-3.5 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div class="flex min-w-0 items-start gap-3.5">
        <span class="flex size-10 shrink-0 items-center justify-center rounded-lg border border-line-subtle bg-raised text-fg-2" aria-hidden="true">
          <component :is="categoryIcon" :size="18" :stroke-width="1.5" />
        </span>
        <div class="min-w-0">
          <p class="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[0.6875rem] leading-4 font-medium tracking-[0.08em] text-fg-3 uppercase">
            {{ categoryLabel }}
            <span class="font-normal tracking-normal normal-case" aria-hidden="true">·</span>
            <span class="flex items-center gap-1 font-mono tracking-normal normal-case">
              {{ memory.id }}
              <Tooltip :delay-duration="200">
                <TooltipTrigger as-child>
                  <button
                    type="button"
                    class="inline-flex size-5 items-center justify-center rounded text-fg-3 transition-colors hover:bg-raised hover:text-fg-1"
                    :aria-label="copied ? 'Memory ID copied' : `Copy memory ID ${memory.id}`"
                    @click="copyId"
                  >
                    <Check v-if="copied" :size="11" :stroke-width="2" class="text-ok" aria-hidden="true" />
                    <Copy v-else :size="11" :stroke-width="1.75" aria-hidden="true" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom" :side-offset="4" class="!text-xs">
                  {{ copied ? `Copied ${memory.id}` : "Copy memory ID" }}
                </TooltipContent>
              </Tooltip>
            </span>
          </p>
          <div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <h1 class="ix-page-title text-fg-1 text-pretty">{{ detail.title }}</h1>
            <MemoryStatusPill :status="memory.status" />
          </div>
          <p class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs leading-4 text-fg-3">
            <span>Updated {{ memoryRelativeTime(memory.updatedAt) }}</span>
            <span aria-hidden="true">·</span>
            <span>Revision <span class="font-mono tabular-nums">r{{ detail.lifecycleRevision }}</span></span>
            <span aria-hidden="true">·</span>
            <span class="inline-flex items-center gap-1">
              Last verified
              <MemoryEmptyValue v-if="!detail.lastVerifiedAt" />
              <span v-else class="font-mono tabular-nums">{{ memoryRelativeTime(detail.lastVerifiedAt) }}</span>
            </span>
          </p>
        </div>
      </div>

      <div class="flex shrink-0 flex-wrap items-center gap-2">
        <GovernDataSourceChip state="illustrative" @open="about?.open()" />
        <GovernAboutPopover
          ref="about"
          state="illustrative"
          verdict="This memory is a recorded design fixture. Its content, provenance, retrieval history, and lifecycle are illustrative; no live memory or tenant content was observed."
          contract="operator.memories.detail.v1 + retrieval history [NEEDS-BACKEND]"
          scope="org_demo_42 · all scopes"
          :range="`Memory ${memoryId} · fixture clock`"
          coverage="0% live · illustrative memory"
          :notes="[
            { lead: 'Inclusion is not influence.', body: 'A retrieval that placed this memory in context does not measure whether the answer used it.' },
            { lead: 'A missing finding is not proof.', body: 'An empty safety cell means no finding is recorded, not that the memory is certified safe.' },
            { lead: 'Read-only.', body: 'Archive, delete, and pin require a privileged write contract.' },
          ]"
        />
        <NuxtLink v-if="sourceSession" :to="sourceSession" class="ix-button-secondary h-8 gap-1.5 px-3 text-xs">
          Open source session
          <ArrowUpRight :size="12" :stroke-width="1.75" aria-hidden="true" />
        </NuxtLink>
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <button
              type="button"
              class="inline-flex size-8 items-center justify-center rounded-md border border-line bg-surface text-fg-2 transition-colors hover:border-line-strong hover:text-fg-1"
              aria-label="More memory actions"
            >
              <Ellipsis :size="15" :stroke-width="1.75" aria-hidden="true" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" class="!w-60">
            <DropdownMenuLabel class="text-xs text-fg-3">Record</DropdownMenuLabel>
            <DropdownMenuItem value="copy-id" class="!text-xs" @select="copyId">
              <Copy :size="13" :stroke-width="1.75" aria-hidden="true" />
              {{ copied ? "Copied memory ID" : "Copy memory ID" }}
            </DropdownMenuItem>
            <DropdownMenuItem value="raw-json" class="!text-xs items-start" @select="emit('show-raw-json')">
              <FileJson :size="13" :stroke-width="1.75" class="mt-0.5" aria-hidden="true" />
              <span>
                View raw JSON
                <span class="mt-0.5 block text-[0.625rem] leading-3.5 text-fg-3">Overview → Technical details</span>
              </span>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem value="archive" disabled class="!text-xs">
              <Lock :size="13" :stroke-width="1.75" aria-hidden="true" />
              Archive
            </DropdownMenuItem>
            <DropdownMenuItem value="delete" disabled class="!text-xs !text-crit/70">
              <Lock :size="13" :stroke-width="1.75" aria-hidden="true" />
              Delete
            </DropdownMenuItem>
            <p class="border-t border-line-subtle px-2 py-2 text-[0.625rem] leading-3.5 text-fg-3">
              Read-only console. Requires a privileged write contract.
            </p>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>

    <div class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <MemoryStatTile label="Confidence" :value="memory.confidence.toFixed(2)" :helper="detail.confidenceMeaning.definition ?? undefined">
        <MemoryScoreBar :value="memory.confidence" label="Extraction confidence" />
      </MemoryStatTile>
      <MemoryStatTile label="Composite score" :value="detail.retrieval.avgComposite.toFixed(2)" helper="Blended rank signal">
        <MemoryScoreBar :value="detail.retrieval.avgComposite" color="bg-viz-2" label="Composite score" />
      </MemoryStatTile>
      <MemoryStatTile
        label="Retrievals"
        :value="String(detail.retrieval.count)"
        :helper="`${linkedSessions.length} ${linkedSessions.length === 1 ? 'session' : 'sessions'} · last ${memoryRelativeTime(memory.lastRetrievedAt) || '—'}`"
      />
      <MemoryStatTile label="In context" :value="`${includedCount} of ${linkedSessions.length}`" helper="Included in context">
        <MemoryScoreBar
          v-if="linkedSessions.length"
          :value="includedCount / linkedSessions.length"
          color="bg-memory"
          label="Context inclusion rate"
        />
      </MemoryStatTile>
    </div>
  </header>
</template>
