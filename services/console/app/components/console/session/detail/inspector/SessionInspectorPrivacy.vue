<script setup lang="ts">
import { computed } from "vue"
import { ScanSearch, ShieldCheck } from "@lucide/vue"
import type { SessionRound } from "@/lib/session-preview"
import { CAPTURE_MODE_LABELS, COMPLETENESS_LABELS, sessionPrivacy } from "@/lib/session-detail"
import MemoryInfoHint from "@/components/console/memory/primitives/MemoryInfoHint.vue"
import SessionCaveat from "../primitives/SessionCaveat.vue"
import SessionRawRecord from "../primitives/SessionRawRecord.vue"

const props = defineProps<{ round: SessionRound }>()

const privacy = computed(() => sessionPrivacy(props.round))
const occurrences = computed(() => privacy.value.pii.findings.reduce((sum, finding) => sum + finding.occurrences, 0))

function entityLabel(entity: string): string {
  return entity
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
}
</script>

<template>
  <div class="space-y-5">
    <section class="grid grid-cols-2 gap-2" aria-label="Capture and redaction state">
      <div class="rounded-lg border border-line-subtle bg-surface px-3 py-2.5">
        <p class="text-[0.6875rem] leading-4 text-fg-3">Capture mode</p>
        <p class="mt-0.5 font-mono text-sm leading-5 text-fg-1">{{ CAPTURE_MODE_LABELS[privacy.captureMode] }}</p>
      </div>
      <div class="rounded-lg border border-line-subtle bg-surface px-3 py-2.5">
        <p class="text-[0.6875rem] leading-4 text-fg-3">Completeness</p>
        <p class="mt-0.5 font-mono text-sm leading-5" :class="privacy.completeness === 'complete' ? 'text-fg-1' : 'text-warn'">
          {{ COMPLETENESS_LABELS[privacy.completeness] }}
        </p>
      </div>
      <div class="rounded-lg border border-line-subtle bg-surface px-3 py-2.5">
        <p class="text-[0.6875rem] leading-4 text-fg-3">Redaction class</p>
        <p class="mt-0.5 font-mono text-sm leading-5" :class="privacy.redactionClass === 'redacted' ? 'text-warn' : 'text-fg-1'">
          {{ privacy.redactionClass }}
        </p>
      </div>
      <div class="rounded-lg border border-line-subtle bg-surface px-3 py-2.5">
        <p class="text-[0.6875rem] leading-4 text-fg-3">Read-path PII guard</p>
        <p class="mt-0.5 inline-flex items-center gap-1.5 font-mono text-sm leading-5 text-ok">
          <ShieldCheck :size="13" :stroke-width="1.9" aria-hidden="true" />
          passed
        </p>
      </div>
    </section>

    <section aria-labelledby="session-pii-findings">
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="session-pii-findings" class="flex items-center gap-1.5 text-[0.8125rem] leading-5 font-medium text-fg-1">
          <ScanSearch :size="13" :stroke-width="1.75" class="text-fg-3" aria-hidden="true" />
          PII findings
        </h3>
        <span class="font-mono text-[0.6875rem] leading-4 text-fg-3 tabular-nums">
          threshold {{ privacy.pii.threshold.toFixed(2) }} · {{ occurrences }} {{ occurrences === 1 ? "entity" : "entities" }}
        </span>
      </div>

      <div v-if="privacy.pii.findings.length" class="ix-scroll mt-2 overflow-x-auto rounded-lg border border-line-subtle bg-surface" tabindex="0" role="region" aria-label="PII findings">
        <table class="w-full min-w-[30rem] text-left text-xs">
          <thead class="border-b border-line-subtle text-[0.625rem] tracking-[0.08em] text-fg-3 uppercase">
            <tr>
              <th scope="col" class="px-3 py-2 font-medium">Entity</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Score</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Count</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Action</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-line-subtle">
            <tr v-for="finding in privacy.pii.findings" :key="finding.entity">
              <td class="px-3 py-2 font-mono text-[0.6875rem] text-fg-1">{{ entityLabel(finding.entity) }}</td>
              <td class="px-3 py-2 text-right font-mono text-fg-2 tabular-nums">{{ finding.score.toFixed(2) }}</td>
              <td class="px-3 py-2 text-right font-mono text-fg-2 tabular-nums">{{ finding.occurrences }}</td>
              <td class="px-3 py-2 text-right">
                <span
                  class="inline-flex h-5 items-center rounded-full border px-2 text-[0.625rem] font-medium"
                  :class="
                    finding.action === 'redacted'
                      ? 'border-ok/30 bg-ok-tint text-ok'
                      : finding.action === 'quarantined'
                        ? 'border-warn/35 bg-warn-tint text-warn'
                        : 'border-line bg-raised text-fg-2'
                  "
                >
                  {{ finding.action }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="mt-2 rounded-lg border border-dashed border-line px-3 py-3 text-xs leading-4 text-fg-3">
        No PII entity passed the analyzer threshold in this turn.
      </p>
    </section>

    <section v-if="privacy.droppedFields.length" aria-labelledby="session-redacted-fields">
      <h3 id="session-redacted-fields" class="text-[0.8125rem] leading-5 font-medium text-fg-1">Removed before storage</h3>
      <ul class="mt-2 flex flex-wrap gap-1.5">
        <li
          v-for="field in privacy.droppedFields"
          :key="field"
          class="rounded border border-line-subtle bg-raised px-1.5 py-0.5 font-mono text-[0.625rem] leading-4 text-fg-2"
        >
          {{ field }}
        </li>
      </ul>
      <p class="mt-2 text-xs leading-4 text-fg-3 text-pretty">{{ privacy.note }}</p>
    </section>

    <div class="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs leading-4 text-fg-3">
      <span>Proof version</span>
      <span class="font-mono text-fg-2">{{ privacy.redactionProofVersion }}</span>
      <MemoryInfoHint label="About redaction proof">
        The proof version is recorded by the session evidence sanitizer. A redacted row is persisted as non-projectable
        evidence; this page never upgrades it to metadata.
      </MemoryInfoHint>
    </div>

    <SessionCaveat
      summary="Redacted is not the same as complete."
      detail="A redacted row means fields were removed before storage. The record can still be read as metadata, but missing content is policy, not a gap in collection."
    />

    <SessionRawRecord :value="round" />
  </div>
</template>
