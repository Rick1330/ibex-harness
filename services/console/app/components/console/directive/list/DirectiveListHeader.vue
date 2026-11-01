<script setup lang="ts">
import { Plus } from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import GovernInfoHint from "@/components/console/govern/primitives/GovernInfoHint.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import { directives } from "@/lib/directive-preview"

const notes = [
  {
    lead: "A directive is instruction text. A policy is a guardrail.",
    body: "A directive has versions (v1…vN) and becomes live by approval. A policy is an immutable snapshot of rules that decides allow, block, ask, redact, wrap, or delete.",
  },
  {
    lead: "Diffs are section-aware.",
    body: "Each version is compared by named section, then by line and word, so a one-word change is visible without reading the whole directive.",
  },
  {
    lead: "Usage stays empty until it is reported.",
    body: "Session and error-rate splits by version need a usage contract; until then they render as not reported rather than as zero.",
  },
]
</script>

<template>
  <ConsolePageHeader
    title="Directives"
    definition="The instructions each agent follows. Every change is a new version that must pass checks and get approval before it goes live."
    state="illustrative"
    :verdict="`Preview renders ${directives.length} directive records with their versions, checks, approvals, section diffs, and audit trail. Promotion, approval, and rollback writes are not connected.`"
    contract="operator.directives.versions.v1 [NEEDS-BACKEND]"
    scope="org_demo_42 · workspace ws_42"
    range="v9 → v14 · 4 directives"
    coverage="0% live · illustrative only"
    :notes="notes"
    :cross-link="{ text: 'Directives tell an agent what to do. Policies decide what it is allowed to do.', href: '/policies', label: 'Open policies' }"
  >
    <template #actions>
      <GovernLockedAction label="New directive" :icon="Plus" variant="primary" />
    </template>

    <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs leading-4 text-fg-3">
      <span class="inline-flex items-center gap-1.5">
        <span class="size-1.5 rounded-full bg-ok" aria-hidden="true" />
        Live = serving traffic
      </span>
      <span class="inline-flex items-center gap-1.5">
        <span class="size-1.5 rounded-full bg-warn" aria-hidden="true" />
        Candidate = waiting to replace live
      </span>
      <span class="inline-flex items-center gap-1.5">
        <span class="size-1.5 rounded-full bg-crit" aria-hidden="true" />
        Failed check = cannot promote
      </span>
      <GovernInfoHint label="How directives differ from policies">
        A directive is versioned instruction text. A policy is a set of guardrail rules published in immutable snapshots.
      </GovernInfoHint>
    </div>
  </ConsolePageHeader>
</template>
