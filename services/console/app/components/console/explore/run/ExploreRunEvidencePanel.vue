<script setup lang="ts">
import { computed } from "vue"
import type { PublicOperatorTraceDetail } from "~~/shared/operator/public"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import { formatDuration } from "@/lib/format"
import { formatGovernNumber, formatGovernStampMillis } from "@/lib/govern-format"
import {
  COMPLETENESS_LABELS,
  COMPLETENESS_MEANING,
  FRESHNESS_LABELS,
  FRESHNESS_MEANING,
  PUBLICATION_LABELS,
  PUBLICATION_MEANING,
  RETENTION_LABELS,
  RETENTION_MEANING,
  completenessClass,
  freshnessClass,
  publicationClass,
} from "@/lib/explore-view"

const props = defineProps<{ detail: PublicOperatorTraceDetail }>()

const evidence = computed(() => props.detail.evidence)

const rows = computed(() => {
  const value = evidence.value
  return [
    {
      key: "completeness",
      label: "Completeness",
      value: COMPLETENESS_LABELS[value.completeness],
      meaning: COMPLETENESS_MEANING[value.completeness],
      klass: completenessClass(value.completeness),
    },
    {
      key: "publication",
      label: "Publication",
      value: PUBLICATION_LABELS[value.publication_state],
      meaning: PUBLICATION_MEANING[value.publication_state],
      klass: publicationClass(value.publication_state),
    },
    {
      key: "freshness",
      label: "Freshness",
      value: FRESHNESS_LABELS[value.freshness],
      meaning: FRESHNESS_MEANING[value.freshness],
      klass: freshnessClass(value.freshness),
    },
    {
      key: "redaction",
      label: "Redaction",
      value:
        value.completeness === "redacted" || value.capture_mode === "redacted" ? "Applied before storage" : "Not recorded",
      meaning: "Fields were removed before storage. Metadata remains readable; content does not.",
      klass:
        value.completeness === "redacted" || value.capture_mode === "redacted" ? "text-warn" : "text-fg-2",
    },
    {
      key: "retention",
      label: "Retention",
      value: RETENTION_LABELS[value.retention],
      meaning: RETENTION_MEANING[value.retention],
      klass: value.retention === "unknown" ? "text-fg-3" : "text-fg-1",
    },
  ]
})

const sourceRows = computed(() => {
  const value = evidence.value
  return [
    { key: "schema", label: "Schema", value: value.schema_version, meaning: "Which validated shape this payload was parsed as." },
    { key: "policy", label: "Read policy", value: value.policy_version, meaning: "The read policy that produced this record." },
    { key: "source", label: "Source", value: value.source, meaning: "The store this evidence row was read from." },
    {
      key: "watermark",
      label: "Watermark",
      value: value.source_watermark === "not_provided" ? "Not recorded" : value.source_watermark,
      meaning: "The outbox sequence the row was written at. 'not_provided' is a recorded value, not a missing one.",
    },
    {
      key: "sample",
      label: "Sample decision",
      value: value.sample_decision,
      meaning: "Why this run was or was not sampled. Verbatim from the collector.",
    },
    { key: "capture", label: "Capture mode", value: value.capture_mode, meaning: "Which capture path produced this record." },
    {
      key: "lag",
      label: "Ingestion lag",
      value: value.ingestion_lag_ms === null ? "Not recorded" : formatDuration(value.ingestion_lag_ms),
      meaning: "Delay between the run and this evidence row becoming readable.",
    },
    { key: "observed", label: "Observed", value: formatGovernStampMillis(value.observed_at), meaning: "When the platform read this evidence row." },
  ]
})
</script>

<template>
  <section class="flex min-w-0 flex-col gap-3" aria-label="Evidence record">
    <div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
      <div
        v-for="row in rows"
        :key="row.key"
        class="min-w-0 rounded-lg border border-line-subtle bg-surface px-3.5 py-3"
        :title="row.meaning"
      >
        <p class="text-[0.6875rem] leading-4 text-fg-3">{{ row.label }}</p>
        <p class="mt-1 truncate font-mono text-sm leading-5" :class="row.klass">{{ row.value }}</p>
        <p class="mt-1 text-[0.6875rem] leading-4 text-fg-3">{{ row.meaning }}</p>
      </div>
    </div>

    <div class="min-w-0 overflow-hidden rounded-lg border border-line-subtle bg-surface">
      <p class="border-b border-line-subtle px-3.5 py-2 text-xs font-medium text-fg-1">Provenance, as recorded</p>
      <dl class="divide-y divide-line-subtle px-3.5">
        <div v-for="row in sourceRows" :key="row.key" class="flex items-baseline justify-between gap-3 py-1.5">
          <dt class="shrink-0 text-[0.6875rem] text-fg-3" :title="row.meaning">{{ row.label }}</dt>
          <dd class="min-w-0 truncate text-right font-mono text-xs leading-5 text-fg-1" :title="`${row.value} · ${row.meaning}`">{{ row.value }}</dd>
        </div>
      </dl>
    </div>

    <GovernCaveat tone="info" title="Freshness is about the read, not the run">
      A stale evidence row means this surface read a record older than its own bound; it does not mean the run
      misbehaved. {{ formatGovernNumber(detail.spans.length) }} span rows were returned with this evidence record — the
      timeline lens is where they are read.
    </GovernCaveat>
  </section>
</template>
