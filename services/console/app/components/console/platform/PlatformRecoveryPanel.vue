<script setup lang="ts">
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernPendingData from "@/components/console/govern/primitives/GovernPendingData.vue"
import { shortDigest } from "@/lib/govern-format"
import type { PlatformDigest, PlatformField } from "@/lib/platform-view"

const props = defineProps<{
  fields: PlatformField[]
  digest: PlatformDigest
  resolved: boolean
}>()

const VALUE_CLASS = {
  default: "text-fg-1",
  warning: "text-warn",
  muted: "text-fg-3",
} as const
</script>

<template>
  <section class="flex min-w-0 flex-col gap-3" aria-label="Recovery and deployment evidence">
    <div class="divide-y divide-line-subtle rounded-lg border border-line-subtle bg-surface">
      <div v-for="field in props.fields" :key="field.label" class="flex items-start gap-4 px-3.5 py-3">
        <div class="w-52 shrink-0">
          <p class="text-xs font-medium text-fg-1">{{ field.label }}</p>
          <p class="mt-0.5 font-mono text-[0.6875rem] leading-4" :class="VALUE_CLASS[field.tone]">
            {{ field.value }}
          </p>
        </div>
        <p class="min-w-0 flex-1 text-[0.6875rem] leading-4 text-fg-3">{{ field.detail }}</p>
      </div>

      <div class="flex items-start gap-4 px-3.5 py-3">
        <div class="w-52 shrink-0">
          <p class="text-xs font-medium text-fg-1">Deployed image digest</p>
          <p v-if="props.digest.value" class="mt-0.5 min-w-0">
            <GovernCopyId
              :id="props.digest.value"
              label="deployed image digest"
              :display="shortDigest(props.digest.value)"
              truncate
            />
          </p>
          <p v-else class="mt-0.5 font-mono text-[0.6875rem] leading-4 text-fg-3">Not recorded</p>
        </div>
        <p class="min-w-0 flex-1 text-[0.6875rem] leading-4 text-fg-3">{{ props.digest.detail }}</p>
      </div>
    </div>

    <div v-if="props.resolved" class="grid gap-2 sm:grid-cols-2">
      <GovernPendingData
        title="Restore drill history"
        contract="operator.platform.drills.history.v1"
        description="The snapshot carries one drill record, not the series. Nothing here shows how long it has been since the last successful restore."
      />
      <GovernPendingData
        title="Backup verification"
        contract="operator.platform.backups.v1"
        description="A recorded backup time is a claim that a backup ran. Verification that it can be read back is a separate contract."
      />
    </div>

    <GovernCaveat tone="warning" title="A backup without a drill is not a recovery plan">
      {{
        props.resolved
          ? "Last backup and last restore drill are two different fields. The first says work was scheduled and ran; only the second says the data was read back. When the drill is not recorded, this page says so in the same voice as every other value."
          : "No snapshot was read, so recovery evidence is unreported rather than assumed. Recovery claims need a recorded drill, and there is none to quote."
      }}
    </GovernCaveat>
  </section>
</template>
