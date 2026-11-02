<script setup lang="ts">
import { computed } from "vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import LiveSessionStatusPill from "./LiveSessionStatusPill.vue"
import { formatGovernNumber, formatGovernStamp } from "@/lib/govern-format"
import type { OperatorSessionTurn } from "~~/shared/operator/contracts"
import type { PublicOperatorSessionRecordDetail } from "~~/shared/operator/public"

const props = defineProps<{ session: PublicOperatorSessionRecordDetail; returnTo: string }>()

const shortId = computed(() => `${props.session.id.slice(0, 8)}…${props.session.id.slice(-4)}`)
const turns = computed<OperatorSessionTurn[]>(() => props.session.turns)

function traceHref(turn: OperatorSessionTurn): string | null {
  if (!turn.trace) return null
  // Carry the list the operator came from, so Explore's back action returns to
  // this session and the session's own back action still returns to the list.
  const session = `/sessions/${encodeURIComponent(props.session.id)}`
  const back = props.returnTo && props.returnTo !== session
    ? `${session}?return=${encodeURIComponent(props.returnTo)}`
    : session
  return `/explore/t/${encodeURIComponent(turn.trace.trace_id)}?return=${encodeURIComponent(back)}`
}

function turnFlags(turn: OperatorSessionTurn): string {
  const flags = [turn.is_streaming ? "streaming" : "buffered"]
  flags.push(turn.is_complete ? "complete" : "partial")
  return flags.join(" · ")
}
</script>

<template>
  <div class="flex min-w-0 flex-col gap-5">
    <ConsolePageHeader
      :title="`Session ${shortId}`"
      definition="Status, counters, provenance, and the turn-to-trace ledger for one agent session."
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
    </ConsolePageHeader>

    <section class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="Session counters">
      <GovernStatTile
        label="Turns"
        :value="formatGovernNumber(session.turn_count)"
        :helper="`${turns.length} recorded on this page`"
      />
      <GovernStatTile
        label="Tokens"
        :value="`${formatGovernNumber(session.total_input_tokens)} / ${formatGovernNumber(session.total_output_tokens)}`"
        helper="Input / output"
      />
      <GovernStatTile
        label="Latency"
        :value="`${formatGovernNumber(session.total_latency_ms)} ms`"
        helper="Sum of recorded turns"
      />
      <GovernStatTile
        label="Evidence fence"
        :value="String(session.evidence_fence_version)"
        :helper="`Lifecycle revision ${session.lifecycle_revision}`"
      />
    </section>

    <section class="grid grid-cols-1 gap-4 lg:grid-cols-3" aria-label="Session metadata">
      <div class="rounded-lg border border-line-subtle bg-surface p-4 lg:col-span-2">
        <h2 class="ix-heading text-fg-1">Identity and provenance</h2>
        <dl class="mt-3 grid grid-cols-1 gap-x-8 gap-y-3 sm:grid-cols-2">
          <div>
            <dt class="ix-label">Session ID</dt>
            <dd class="mt-0.5 break-all font-mono text-xs text-fg-1">{{ session.id }}</dd>
          </div>
          <div>
            <dt class="ix-label">Agent ID</dt>
            <dd class="mt-0.5 break-all font-mono text-xs text-fg-1">{{ session.agent_id }}</dd>
          </div>
          <div>
            <dt class="ix-label">External ID</dt>
            <dd class="mt-0.5 break-all font-mono text-xs text-fg-1">{{ session.external_id ?? "Not set" }}</dd>
          </div>
          <div>
            <dt class="ix-label">Directive version</dt>
            <dd class="mt-0.5 break-all font-mono text-xs text-fg-1">{{ session.directive_version_id ?? "Not pinned" }}</dd>
          </div>
          <div>
            <dt class="ix-label">Model</dt>
            <dd class="mt-0.5 text-xs text-fg-1">{{ session.model }}</dd>
          </div>
          <div>
            <dt class="ix-label">Provider</dt>
            <dd class="mt-0.5 text-xs text-fg-1">{{ session.provider }}</dd>
          </div>
          <div>
            <dt class="ix-label">Created</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1">{{ formatGovernStamp(session.created_at) }}</dd>
          </div>
          <div>
            <dt class="ix-label">Completed</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1">{{ formatGovernStamp(session.completed_at) }}</dd>
          </div>
        </dl>
      </div>

      <div class="rounded-lg border border-line-subtle bg-surface p-4">
        <h2 class="ix-heading text-fg-1">Extraction</h2>
        <dl class="mt-3 flex flex-col gap-3">
          <div>
            <dt class="ix-label">Last extracted turn</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1">
              {{ formatGovernNumber(session.last_extracted_turn) }} / {{ formatGovernNumber(session.turn_count) }}
            </dd>
          </div>
          <div>
            <dt class="ix-label">Updated</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1">{{ formatGovernStamp(session.updated_at) }}</dd>
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

      <p v-if="turns.length === 0" class="rounded-lg border border-dashed border-line-subtle bg-surface p-4 text-xs text-fg-3">
        No checkpoints are recorded for this session yet.
      </p>

      <div v-else class="overflow-x-auto rounded-lg border border-line-subtle bg-surface">
        <table class="ix-agent-table" aria-label="Session turns">
          <caption class="sr-only">Ordered turn ledger with the linked evidence trace when one exists.</caption>
          <thead>
            <tr>
              <th scope="col" class="!pl-4 w-16 text-right">Turn</th>
              <th scope="col" class="w-64">Request</th>
              <th scope="col" class="w-28 text-right">Tokens</th>
              <th scope="col" class="w-24 text-right">Latency</th>
              <th scope="col" class="hidden w-36 min-[1000px]:table-cell">Flags</th>
              <th scope="col" class="w-56">Evidence</th>
              <th scope="col" class="w-36">Created</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="turn in turns" :key="turn.id" :data-turn-row="turn.id">
              <td class="!pl-4 text-right font-mono text-xs text-fg-1 tabular-nums">{{ turn.turn_index }}</td>
              <td class="font-mono text-[0.6875rem] break-all text-fg-2">{{ turn.request_id }}</td>
              <td class="text-right font-mono text-xs text-fg-1 tabular-nums">
                {{ formatGovernNumber(turn.input_tokens) }} / {{ formatGovernNumber(turn.output_tokens) }}
              </td>
              <td class="text-right font-mono text-xs text-fg-1 tabular-nums">{{ formatGovernNumber(turn.latency_ms) }} ms</td>
              <td class="hidden text-xs text-fg-3 min-[1000px]:table-cell">{{ turnFlags(turn) }}</td>
              <td class="text-xs">
                <NuxtLink
                  v-if="turn.trace"
                  :to="traceHref(turn) ?? '/explore'"
                  class="font-mono text-[0.6875rem] text-accent-memory underline-offset-3 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                >
                  {{ turn.trace.trace_id.slice(0, 12) }}…
                </NuxtLink>
                <span v-else class="text-fg-3">No evidence</span>
                <span v-if="turn.trace" class="mt-0.5 block text-[0.625rem] text-fg-3">
                  {{ turn.trace.completeness }} · {{ turn.trace.status }}
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
