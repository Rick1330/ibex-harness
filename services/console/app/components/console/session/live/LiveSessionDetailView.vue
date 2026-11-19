<script setup lang="ts">
import { computed } from "vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import GovernIdChip from "@/components/console/govern/primitives/GovernIdChip.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import LiveSessionStatusPill from "./LiveSessionStatusPill.vue"
import { formatGovernNumber, formatGovernStamp } from "@/lib/govern-format"
import {
  formatSessionLatency,
  SESSION_EXTRACTION_NOTE,
  sessionEndLabel,
  sessionExtraction,
  shortId,
} from "@/lib/session-list"
import type { OperatorSessionTurn } from "~~/shared/operator/contracts"
import type { PublicOperatorSessionRecordDetail } from "~~/shared/operator/public"

const props = defineProps<{ session: PublicOperatorSessionRecordDetail; returnTo: string }>()

const turns = computed<OperatorSessionTurn[]>(() => props.session.turns)
const extraction = computed(() => sessionExtraction(props.session.last_extracted_turn, props.session.turn_count))
const extractionHelper = computed(() =>
  extraction.value.index === null ? "No turns recorded" : SESSION_EXTRACTION_NOTE,
)
const extractionValue = computed(() =>
  extraction.value.index === null ? "Not recorded" : formatGovernNumber(extraction.value.index),
)
const agentHref = computed(() => `/agents/${encodeURIComponent(props.session.agent_id)}`)
const tokensLabel = computed(
  () => `${formatGovernNumber(props.session.total_input_tokens)} / ${formatGovernNumber(props.session.total_output_tokens)}`,
)
const turnsHelper = computed(
  () => `${turns.value.length} checkpoint${turns.value.length === 1 ? "" : "s"} on this record`,
)
// `completed_at` is also where the idle sweeper stores its abandon instant, so
// the field is labelled from the status (see `sessionEndLabel`).
const endLabel = computed(() => sessionEndLabel(props.session.status))

function traceHref(turn: OperatorSessionTurn): string | null {
  if (!turn.trace) return null
  // Carry the list the operator came from, so Explore's back action returns to
  // this session and the session's own back action still returns to the list.
  const session = `/sessions/${encodeURIComponent(props.session.id)}`
  const back =
    props.returnTo && props.returnTo !== session
      ? `${session}?return=${encodeURIComponent(props.returnTo)}`
      : session
  return `/explore/t/${encodeURIComponent(turn.trace.trace_id)}?return=${encodeURIComponent(back)}`
}

function turnFlags(turn: OperatorSessionTurn): string {
  const flags = [turn.is_streaming ? "streaming" : "buffered"]
  flags.push(turn.is_complete ? "complete" : "partial")
  return flags.join(" · ")
}

function evidenceNote(turn: OperatorSessionTurn): string {
  if (!turn.trace) return ""
  const parts: string[] = [turn.trace.completeness, turn.trace.status]
  if (turn.trace.error_code) parts.push(turn.trace.error_code)
  return parts.join(" · ")
}
</script>

<template>
  <div class="flex min-w-0 flex-col gap-5">
    <ConsolePageHeader
      :title="`Session ${shortId(session.id)}`"
      state="live"
      :verdict="`Status: ${session.status}`"
      contract="operator.sessions.v1"
      scope="Organization"
      range="Session record"
      :observed="session.updated_at"
      caveat="Message content, hashes, and provider request ids are not part of this contract and are not shown."
    >
      <template #back>
        <NuxtLink :to="returnTo" class="mb-2 inline-flex text-xs text-fg-3 hover:text-fg-1">
          ← Back to sessions
        </NuxtLink>
      </template>
      <template #actions>
        <LiveSessionStatusPill :status="session.status" />
      </template>
      <GovernIdChip :value="session.id" label="Session ID" />
    </ConsolePageHeader>

    <section class="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Session counters">
      <GovernStatTile label="Turns" :value="formatGovernNumber(session.turn_count)" :helper="turnsHelper" />
      <GovernStatTile label="Tokens" :value="tokensLabel" helper="Input / output" />
      <GovernStatTile
        label="Turn latency"
        :value="formatSessionLatency(session.total_latency_ms)"
        helper="Sum of recorded turns"
      />
      <GovernStatTile
        label="Extracted to"
        :value="extractionValue"
        helper="Zero-based turn index"
      />
    </section>

    <section class="grid grid-cols-1 gap-4 lg:grid-cols-3" aria-label="Session provenance">
      <div class="rounded-lg border border-line-subtle bg-surface p-4 lg:col-span-2">
        <h2 class="ix-heading text-fg-1">Identity and provenance</h2>
        <dl class="mt-3 grid grid-cols-1 gap-x-8 gap-y-3 sm:grid-cols-2">
          <div class="min-w-0">
            <dt class="ix-label">Agent ID</dt>
            <dd class="mt-0.5">
              <NuxtLink
                :to="agentHref"
                class="break-all font-mono text-xs text-fg-1 underline decoration-line-strong underline-offset-2 hover:text-accent-memory focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
              >
                {{ session.agent_id }}
              </NuxtLink>
            </dd>
          </div>
          <div class="min-w-0">
            <dt class="ix-label">External ID</dt>
            <dd class="mt-0.5 break-all font-mono text-xs text-fg-1">{{ session.external_id ?? "Not set" }}</dd>
          </div>
          <div class="min-w-0">
            <dt class="ix-label">Model</dt>
            <dd class="mt-0.5 break-all text-xs text-fg-1">{{ session.model }}</dd>
          </div>
          <div class="min-w-0">
            <dt class="ix-label">Provider</dt>
            <dd class="mt-0.5 text-xs text-fg-1">{{ session.provider }}</dd>
          </div>
          <div class="min-w-0">
            <dt class="ix-label">Directive version</dt>
            <dd class="mt-0.5 break-all font-mono text-xs text-fg-1">
              {{ session.directive_version_id ?? "Not pinned" }}
            </dd>
          </div>
          <div class="min-w-0">
            <dt class="ix-label">Created</dt>
            <dd class="mt-0.5 font-mono text-xs whitespace-nowrap text-fg-1">
              {{ formatGovernStamp(session.created_at) }}
            </dd>
          </div>
          <div class="min-w-0">
            <dt class="ix-label">{{ endLabel }}</dt>
            <dd class="mt-0.5 font-mono text-xs whitespace-nowrap text-fg-1">
              {{ formatGovernStamp(session.completed_at) }}
            </dd>
          </div>
          <div class="min-w-0">
            <dt class="ix-label">Updated</dt>
            <dd class="mt-0.5 font-mono text-xs whitespace-nowrap text-fg-1">
              {{ formatGovernStamp(session.updated_at) }}
            </dd>
          </div>
        </dl>
      </div>

      <div class="rounded-lg border border-line-subtle bg-surface p-4">
        <h2 class="ix-heading text-fg-1">Extraction and fences</h2>
        <dl class="mt-3 flex flex-col gap-3">
          <div class="min-w-0">
            <dt class="ix-label">Last extracted turn</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1 tabular-nums">{{ extraction.label }}</dd>
            <dd class="mt-0.5 text-[0.6875rem] leading-4 text-fg-3">{{ extractionHelper }}</dd>
          </div>
          <div class="min-w-0">
            <dt class="ix-label">Lifecycle revision</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1 tabular-nums">{{ session.lifecycle_revision }}</dd>
          </div>
          <div class="min-w-0">
            <dt class="ix-label">Evidence fence version</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1 tabular-nums">{{ session.evidence_fence_version }}</dd>
          </div>
        </dl>
      </div>
    </section>

    <section class="flex min-w-0 flex-col gap-2" aria-label="Session turns">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h2 class="ix-heading text-fg-1">Turns</h2>
        <p v-if="session.turns_truncated" class="text-xs text-warn" role="note">
          Showing the first {{ turns.length }} turns; this session has more.
        </p>
      </div>

      <p
        v-if="turns.length === 0"
        class="rounded-lg border border-dashed border-line-subtle bg-surface p-4 text-xs text-fg-3"
      >
        No checkpoints are recorded for this session yet.
      </p>

      <div v-else class="overflow-x-auto rounded-lg border border-line-subtle bg-surface">
        <table class="ix-agent-table" aria-label="Session turns">
          <caption class="sr-only">
            Ordered turn ledger, one row per recorded turn, with the linked evidence run when one exists. Tokens are
            input / output; latency is the recorded round trip for that turn.
          </caption>
          <thead>
            <tr>
              <th scope="col" class="!pl-4 w-16 text-right">Turn</th>
              <th scope="col" class="w-[20rem]">Request</th>
              <th scope="col" class="w-32 text-right whitespace-nowrap">Tokens</th>
              <th scope="col" class="w-24 text-right">Latency</th>
              <th scope="col" class="w-56">Evidence</th>
              <th scope="col" class="w-40">Created</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="turn in turns" :key="turn.id" :data-turn-row="turn.id">
              <td class="!pl-4 text-right font-mono text-xs text-fg-1 tabular-nums">{{ turn.turn_index }}</td>
              <td>
                <span
                  class="line-clamp-2 block max-w-[20rem] font-mono text-[0.6875rem] leading-4 break-all text-fg-2"
                  :title="turn.request_id"
                >{{ turn.request_id }}</span>
                <span class="mt-0.5 block font-mono text-[0.625rem] leading-4 whitespace-nowrap text-fg-3">{{ turnFlags(turn) }}</span>
              </td>
              <td class="text-right font-mono text-xs whitespace-nowrap text-fg-1 tabular-nums">
                {{ formatGovernNumber(turn.input_tokens) }} / {{ formatGovernNumber(turn.output_tokens) }}
              </td>
              <td class="text-right font-mono text-xs whitespace-nowrap text-fg-1 tabular-nums">
                {{ formatSessionLatency(turn.latency_ms) }}
              </td>
              <td class="text-xs">
                <NuxtLink
                  v-if="turn.trace"
                  :to="traceHref(turn) ?? '/explore'"
                  class="font-mono text-[0.6875rem] whitespace-nowrap text-accent-memory underline-offset-3 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                >
                  {{ shortId(turn.trace.trace_id) }}
                </NuxtLink>
                <span v-else class="text-fg-3">No evidence</span>
                <span v-if="turn.trace" class="mt-0.5 block text-[0.625rem] leading-4 text-fg-3">
                  {{ evidenceNote(turn) }}
                </span>
              </td>
              <td class="text-xs whitespace-nowrap text-fg-2">{{ formatGovernStamp(turn.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
