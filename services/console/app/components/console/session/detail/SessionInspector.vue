<script setup lang="ts">
import { computed, nextTick, ref } from "vue"
import { ArrowUpRight, Check, ChevronLeft, ChevronRight, Circle, PanelRightOpen, TriangleAlert, X } from "@lucide/vue"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { PreviewSession, SessionFocus, SessionRound } from "@/lib/session-preview"
import {
  decisionIcon,
  decisionLabel,
  driftState,
  formatOffset,
  outcomeLabel,
  outcomeTone,
  roundOffsetMs,
  sessionPrivacy,
  turnInsight,
} from "@/lib/session-detail"
import SessionStatusPill from "./primitives/SessionStatusPill.vue"
import SessionInspectorTrace from "./inspector/SessionInspectorTrace.vue"
import SessionInspectorMemories from "./inspector/SessionInspectorMemories.vue"
import SessionInspectorDirective from "./inspector/SessionInspectorDirective.vue"
import SessionInspectorPolicy from "./inspector/SessionInspectorPolicy.vue"
import SessionInspectorDrift from "./inspector/SessionInspectorDrift.vue"
import SessionInspectorPrivacy from "./inspector/SessionInspectorPrivacy.vue"
import BrandIcon from "@/components/console/BrandIcon.vue"

const props = defineProps<{
  session: PreviewSession
  rounds: SessionRound[]
  round: SessionRound
  panel: SessionFocus
  spanId: string | null
  returnTo: string
  /** Unique prefix so a sheet instance never duplicates DOM ids with the inline panel. */
  idPrefix?: string
}>()

const panelId = (id: SessionFocus): string => `${props.idPrefix ?? "session"}-panel-tab-${id}`
const bodyId = (id: SessionFocus): string => `${props.idPrefix ?? "session"}-panel-body-${id}`

const emit = defineEmits<{
  "update:panel": [panel: SessionFocus]
  "update:spanId": [id: string]
  "select-turn": [index: number]
  "step-turn": [delta: number]
  transcript: [spanId: string | null]
  copy: [value: string, label: string]
  hover: [spanId: string | null]
  expand: []
}>()

type PanelConfig = {
  id: SessionFocus
  label: string
  section: string
  href: string
}

const PANELS: PanelConfig[] = [
  { id: "trace", label: "Trace", section: "Traces", href: "/explore" },
  { id: "memories", label: "Memories", section: "Memories", href: "/memories" },
  { id: "directive", label: "Directive", section: "Directives", href: "/directives" },
  { id: "policy", label: "Policy", section: "Policies", href: "/policies" },
  { id: "drift", label: "Drift", section: "Drift", href: "/drift" },
  { id: "privacy", label: "Privacy", section: "Evidence", href: "/evidence" },
]

const tablist = ref<HTMLElement | null>(null)

const headline = computed(() => turnInsight(props.round, props.panel))
const offset = computed(() => formatOffset(roundOffsetMs(props.session, props.round)))
const statusTone = computed(() => outcomeTone(props.round.outcome))
const fullPage = computed(() => PANELS.find((entry) => entry.id === props.panel)!)

const anyIncluded = computed(() => props.round.memories.some((memory) => memory.usedInResponse))
const drift = computed(() => driftState(props.round))
const privacy = computed(() => sessionPrivacy(props.round))

function select(panel: SessionFocus): void {
  emit("update:panel", panel)
}

function onTabKeydown(event: KeyboardEvent): void {
  const last = PANELS.length - 1
  const index = PANELS.findIndex((entry) => entry.id === props.panel)
  let next = index
  if (event.key === "ArrowRight") next = index === last ? 0 : index + 1
  else if (event.key === "ArrowLeft") next = index === 0 ? last : index - 1
  else if (event.key === "Home") next = 0
  else if (event.key === "End") next = last
  else return
  event.preventDefault()
  const panel = PANELS[next]!.id
  emit("update:panel", panel)
  void nextTick(() => {
    tablist.value?.querySelector<HTMLButtonElement>(`[data-session-panel="${panel}"]`)?.focus()
  })
}

function revealSpan(label: string): void {
  const span = props.round.spans.find((item) => item.label === label)
  if (span) emit("update:spanId", span.id)
  emit("update:panel", "trace")
}

function onDriftTurn(index: number): void {
  emit("select-turn", index)
}
</script>

<template>
  <aside class="ix-inspector" aria-label="Turn inspector">
    <header class="ix-inspector-header">
      <div class="flex items-center gap-2">
        <p class="text-[0.8125rem] leading-5 font-medium text-fg-1">
          Turn {{ round.index }} of {{ rounds.length }}
        </p>
        <div class="ml-auto flex items-center gap-0.5">
          <Tooltip :delay-duration="200">
            <TooltipTrigger as-child>
              <button
                type="button"
                class="ix-icon-button"
                :disabled="round.index <= 1"
                aria-label="Previous turn (K)"
                @click="emit('step-turn', -1)"
              >
                <ChevronLeft :size="15" :stroke-width="1.75" aria-hidden="true" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom" :side-offset="4" class="!text-xs">Previous turn (K)</TooltipContent>
          </Tooltip>
          <Tooltip :delay-duration="200">
            <TooltipTrigger as-child>
              <button
                type="button"
                class="ix-icon-button"
                :disabled="round.index >= rounds.length"
                aria-label="Next turn (J)"
                @click="emit('step-turn', 1)"
              >
                <ChevronRight :size="15" :stroke-width="1.75" aria-hidden="true" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom" :side-offset="4" class="!text-xs">Next turn (J)</TooltipContent>
          </Tooltip>
          <Tooltip :delay-duration="200">
            <TooltipTrigger as-child>
              <button type="button" class="ix-icon-button" aria-label="Expand inspector" @click="emit('expand')">
                <PanelRightOpen :size="14" :stroke-width="1.75" aria-hidden="true" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom" :side-offset="4" class="!text-xs">Open as a wider panel</TooltipContent>
          </Tooltip>
        </div>
      </div>

      <div class="mt-1 flex min-w-0 items-center gap-x-2 gap-y-1 overflow-hidden text-xs leading-4 text-fg-3">
        <SessionStatusPill :tone="statusTone" :label="outcomeLabel(round.outcome)" compact />
        <span class="font-mono tabular-nums">{{ offset }}</span>
        <span aria-hidden="true">·</span>
        <span class="font-mono tabular-nums">{{ round.latencyMs }} ms</span>
        <span aria-hidden="true">·</span>
        <span class="inline-flex min-w-0 items-center gap-1"><BrandIcon :id="round.model" :size="12" :label="`${round.model} logo`" /><span class="truncate">{{ round.model }}</span></span>
      </div>
    </header>

    <div ref="tablist" class="ix-inspector-tabs" role="tablist" aria-label="Inspector panels" @keydown="onTabKeydown">
      <button
        v-for="entry in PANELS"
        :id="panelId(entry.id)"
        :key="entry.id"
        type="button"
        role="tab"
        class="ix-inspector-tab"
        :class="panel === entry.id && 'ix-inspector-tab-active'"
        :data-session-panel="entry.id"
        :aria-selected="panel === entry.id"
        :aria-controls="bodyId(entry.id)"
        :tabindex="panel === entry.id ? 0 : -1"
        @click="select(entry.id)"
      >
        <span>{{ entry.label }}</span>

        <span v-if="entry.id === 'trace'" class="ix-badge font-mono" :aria-label="`Trace: ${round.spans.length} spans`">
          {{ round.spans.length }}
        </span>

        <span
          v-else-if="entry.id === 'memories'"
          class="ix-badge font-mono"
          :class="anyIncluded && 'ix-badge-memory'"
          :aria-label="`Memories: ${round.memories.length} retrieved${anyIncluded ? ', at least one included in the reply' : ''}`"
        >
          {{ round.memories.length }}<span v-if="anyIncluded" class="ix-badge-dot" aria-hidden="true" />
        </span>

        <span v-else-if="entry.id === 'directive'" class="ix-badge font-mono" :aria-label="`Directive: ${round.directive.version}`">
          {{ round.directive.version }}
        </span>

        <span
          v-else-if="entry.id === 'policy'"
          class="ix-badge"
          :class="{
            'ix-badge-ok': decisionIcon(round.policy.decision) === 'success',
            'ix-badge-crit': decisionIcon(round.policy.decision) === 'destructive',
            'ix-badge-warn': decisionIcon(round.policy.decision) === 'warning',
          }"
          :aria-label="`Policy: ${decisionLabel(round.policy.decision)}`"
        >
          <Check v-if="decisionIcon(round.policy.decision) === 'success'" :size="10" :stroke-width="2.4" aria-hidden="true" />
          <X v-else-if="decisionIcon(round.policy.decision) === 'destructive'" :size="10" :stroke-width="2.4" aria-hidden="true" />
          <TriangleAlert v-else :size="10" :stroke-width="2" aria-hidden="true" />
        </span>

        <span
          v-else-if="entry.id === 'drift'"
          class="ix-badge"
          :class="{
            'ix-badge-warn': drift === 'advisory',
            'ix-badge-ok': drift === 'clean',
          }"
          :aria-label="`Drift: ${drift === 'advisory' ? 'advisory raised' : drift === 'clean' ? 'checked and clean' : 'not checked'}`"
        >
          <TriangleAlert v-if="drift === 'advisory'" :size="10" :stroke-width="2" aria-hidden="true" />
          <Check v-else-if="drift === 'clean'" :size="10" :stroke-width="2.4" aria-hidden="true" />
          <Circle v-else :size="9" :stroke-width="2" aria-hidden="true" />
        </span>

        <span
          v-else
          class="ix-badge"
          :class="privacy.pii.detected ? 'ix-badge-warn' : 'ix-badge-ok'"
          :aria-label="privacy.pii.detected ? 'Privacy: PII detected' : 'Privacy: no PII recorded'"
        >
          {{ privacy.pii.detected ? "PII" : "OK" }}
        </span>
      </button>
    </div>

    <div class="ix-inspector-body">
      <div
        :id="bodyId(panel)"
        role="tabpanel"
        :aria-labelledby="panelId(panel)"
        class="min-w-0"
      >
        <p class="ix-headline">{{ headline }}</p>

        <SessionInspectorTrace
          v-if="panel === 'trace'"
          :round="round"
          :span-id="spanId"
          :id-prefix="idPrefix ?? 'session'"
          @update:span-id="emit('update:spanId', $event)"
          @navigate="select"
          @hover="emit('hover', $event)"
          @transcript="emit('transcript', $event)"
        />

        <SessionInspectorMemories
          v-else-if="panel === 'memories'"
          :round="round"
          :return-to="returnTo"
          @navigate="revealSpan('memory.retrieve')"
          @transcript="emit('transcript', 'memory.retrieve')"
        />

        <SessionInspectorDirective
          v-else-if="panel === 'directive'"
          :round="round"
          @span="revealSpan"
          @copy="(value, label) => emit('copy', value, label)"
        />

        <SessionInspectorPolicy
          v-else-if="panel === 'policy'"
          :round="round"
          @span="revealSpan"
        />

        <SessionInspectorDrift
          v-else-if="panel === 'drift'"
          :round="round"
          :rounds="rounds"
          @transcript="emit('transcript', null)"
          @select-turn="onDriftTurn"
        />

        <SessionInspectorPrivacy v-else :round="round" />
      </div>
    </div>

    <footer class="ix-inspector-footer">
      <NuxtLink :to="fullPage.href" class="ix-footer-link">
        Open in {{ fullPage.section }}
        <ArrowUpRight :size="12" :stroke-width="1.75" aria-hidden="true" />
      </NuxtLink>
    </footer>
  </aside>
</template>

<style scoped>
.ix-inspector {
  display: flex;
  max-height: 100%;
  min-height: 0;
  flex-direction: column;
  border: 1px solid var(--ix-line-subtle);
  border-radius: 12px;
  background: var(--ix-surface);
  overflow: hidden;
}

.ix-inspector-header {
  flex: none;
  border-bottom: 1px solid var(--ix-line-subtle);
  padding: 0.625rem 0.75rem 0.5rem;
  min-height: 3.5rem;
}

.ix-icon-button {
  display: inline-flex;
  width: 1.75rem;
  height: 1.75rem;
  align-items: center;
  justify-content: center;
  border-radius: 5px;
  color: var(--ix-fg-3);
  transition: background-color 120ms, color 120ms;
}

.ix-icon-button:hover:not(:disabled) {
  background: var(--ix-raised);
  color: var(--ix-fg-1);
}

.ix-icon-button:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.ix-icon-button:focus-visible {
  outline: 2px solid var(--ix-accent-memory);
  outline-offset: 1px;
}

.ix-inspector-tabs {
  display: flex;
  flex: none;
  align-items: stretch;
  gap: 0.125rem;
  overflow-x: auto;
  overflow-y: hidden;
  border-bottom: 1px solid var(--ix-line-subtle);
  padding: 0 0.25rem;
  scrollbar-width: none;
  -webkit-mask-image: linear-gradient(to right, black calc(100% - 1.5rem), transparent);
  mask-image: linear-gradient(to right, black calc(100% - 1.5rem), transparent);
}

.ix-inspector-tabs::-webkit-scrollbar {
  display: none;
}

.ix-inspector-tab {
  position: relative;
  display: inline-flex;
  height: 2.5rem;
  flex: none;
  align-items: center;
  gap: 0.1875rem;
  border-radius: 6px;
  padding: 0 0.1875rem;
  font-size: 0.875rem;
  line-height: 1;
  font-weight: 500;
  color: var(--ix-fg-3);
  white-space: nowrap;
  transition: color 120ms, background-color 120ms;
}

.ix-inspector-tab:hover {
  background: var(--ix-surface-2);
  color: var(--ix-fg-1);
}

.ix-inspector-tab-active {
  background: transparent;
  color: var(--ix-fg-1);
}

.ix-inspector-tab-active::after {
  content: "";
  position: absolute;
  right: 0.1875rem;
  bottom: 0;
  left: 0.1875rem;
  height: 2px;
  border-radius: 2px 2px 0 0;
  background: var(--ix-accent-memory);
}

.ix-inspector-tab:focus-visible {
  outline: 2px solid var(--ix-accent-memory);
  outline-offset: -2px;
}

.ix-badge {
  display: inline-flex;
  height: 1.125rem;
  min-width: 1.125rem;
  align-items: center;
  justify-content: center;
  gap: 0.125rem;
  border-radius: 9px;
  background: var(--ix-surface-2);
  padding: 0 0.3125rem;
  font-size: 0.6875rem;
  line-height: 1;
  color: var(--ix-fg-2);
}

.ix-badge-dot {
  width: 0.25rem;
  height: 0.25rem;
  border-radius: 9999px;
  background: var(--ix-memory);
}

.ix-badge-memory {
  color: var(--ix-fg-1);
}

.ix-badge-ok {
  background: var(--ix-ok-tint);
  color: var(--ix-ok);
}

.ix-badge-warn {
  background: var(--ix-warn-tint);
  color: var(--ix-warn);
}

.ix-badge-crit {
  background: var(--ix-crit-tint);
  color: var(--ix-crit);
}

.ix-inspector-body {
  min-height: 0;
  flex: 1 1 auto;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 0.875rem 0.875rem 1rem;
}

.ix-headline {
  margin-bottom: 0.875rem;
  font-size: 0.9375rem;
  line-height: 1.375rem;
  font-weight: 600;
  color: var(--ix-fg-1);
  text-wrap: pretty;
}

.ix-inspector-footer {
  display: flex;
  flex: none;
  height: 3rem;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  border-top: 1px solid var(--ix-line-subtle);
  padding: 0 0.75rem;
}

.ix-footer-link {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 0.25rem;
  border-radius: 4px;
  font-size: 0.6875rem;
  line-height: 1rem;
  font-weight: 500;
  color: var(--ix-fg-2);
  white-space: nowrap;
  transition: color 120ms;
}

.ix-footer-link:hover {
  color: var(--ix-fg-1);
}

.ix-footer-link:focus-visible {
  outline: 2px solid var(--ix-accent-memory);
  outline-offset: 2px;
}

@media (max-width: 480px) {
  .ix-inspector-tab {
    height: 2.25rem;
    gap: 0.125rem;
    padding: 0 0.0625rem;
    font-size: 0.75rem;
  }

  .ix-badge {
    height: 1rem;
    min-width: 1rem;
    padding: 0 0.25rem;
    font-size: 0.625rem;
  }

  .ix-inspector-body {
    padding-right: 0.75rem;
    padding-left: 0.75rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ix-icon-button,
  .ix-inspector-tab {
    transition-duration: 1ms;
  }
}
</style>