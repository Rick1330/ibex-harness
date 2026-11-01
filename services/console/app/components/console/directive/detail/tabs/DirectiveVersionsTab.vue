<script setup lang="ts">
import { computed } from "vue"
import { ArrowLeftRight, ScrollText } from "@lucide/vue"
import GovernEmptyValue from "@/components/console/govern/primitives/GovernEmptyValue.vue"
import GovernHashTag from "@/components/console/govern/primitives/GovernHashTag.vue"
import GovernLifecyclePill from "@/components/console/govern/primitives/GovernLifecyclePill.vue"
import GovernVersionTag from "@/components/console/govern/primitives/GovernVersionTag.vue"
import {
  directiveApprovalState,
  directiveCheckSummary,
  type Directive,
  type DirectiveVersion,
} from "@/lib/directive-preview"
import { formatGovernDate, formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"

const props = defineProps<{ directive: Directive }>()
const emit = defineEmits<{ compare: [from: string, to: string]; audit: [] }>()

const versions = computed(() => props.directive.versions)

function previous(version: DirectiveVersion): DirectiveVersion | null {
  const index = versions.value.findIndex((entry) => entry.version === version.version)
  return index >= 0 ? versions.value[index + 1] ?? null : null
}

function compare(version: DirectiveVersion): void {
  const before = previous(version)
  if (!before) return
  emit("compare", before.version, version.version)
}

function checksTone(version: DirectiveVersion): string {
  const summary = directiveCheckSummary(version)
  if (summary.failed) return "text-crit"
  if (summary.pending) return "text-warn"
  if (summary.total && summary.passed === summary.total) return "text-ok"
  return "text-fg-3"
}

function liveWindow(version: DirectiveVersion): string {
  if (!version.liveFrom) return "Never live"
  const start = formatGovernDate(version.liveFrom)
  if (!version.liveTo) return `${start} → now`
  return `${start} → ${formatGovernDate(version.liveTo)}`
}
</script>

<template>
  <div class="min-w-0 space-y-4">
    <div class="hidden overflow-hidden rounded-lg border border-line-subtle bg-surface-1 min-[900px]:block">
      <div class="ix-scroll overflow-x-auto">
        <table class="ix-agent-table" aria-label="Directive versions">
          <thead>
            <tr>
              <th scope="col" class="!pl-4">Version</th>
              <th scope="col">State</th>
              <th scope="col">Author</th>
              <th scope="col">Created</th>
              <th scope="col">Live window</th>
              <th scope="col">Checks</th>
              <th scope="col">Approvals</th>
              <th scope="col">Digest</th>
              <th scope="col" class="w-24"><span class="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="version in versions" :key="version.version">
              <td class="!pl-4">
                <GovernVersionTag label="Version" :value="version.version" tone="default" />
                <p v-if="version.summary" class="mt-0.5 max-w-[30ch] truncate text-[0.6875rem] leading-4 text-fg-3" :title="version.summary">{{ version.summary }}</p>
                <p v-else class="mt-0.5 text-[0.6875rem] leading-4 text-fg-3"><GovernEmptyValue reason="No change note" /></p>
              </td>
              <td><GovernLifecyclePill :state="version.state" /></td>
              <td class="truncate">{{ version.author }}</td>
              <td class="whitespace-nowrap" :title="formatGovernStamp(version.createdAt)">{{ formatGovernRelative(version.createdAt) }}</td>
              <td class="whitespace-nowrap text-[0.6875rem]">{{ liveWindow(version) }}</td>
              <td class="whitespace-nowrap font-mono text-[0.6875rem] tabular-nums" :class="checksTone(version)">
                {{ directiveCheckSummary(version).total ? directiveCheckSummary(version).label : "Not configured" }}
              </td>
              <td class="whitespace-nowrap font-mono text-[0.6875rem] text-fg-3 tabular-nums">
                {{ directiveApprovalState(version).required ? `${directiveApprovalState(version).approved}/${directiveApprovalState(version).required}` : "—" }}
              </td>
              <td><GovernHashTag :hash="version.hash" label="digest" /></td>
              <td class="pr-3">
                <div class="flex items-center justify-end gap-1">
                  <button
                    type="button"
                    class="ix-row-action !opacity-100"
                    :disabled="!previous(version)"
                    :aria-label="previous(version) ? `Compare ${previous(version)!.version} with ${version.version}` : `No earlier version to compare with ${version.version}`"
                    @click="compare(version)"
                  >
                    <ArrowLeftRight :size="13" :stroke-width="1.9" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    class="ix-row-action !opacity-100"
                    :aria-label="`Open audit for ${version.version}`"
                    @click="emit('audit')"
                  >
                    <ScrollText :size="13" :stroke-width="1.9" aria-hidden="true" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="flex flex-col gap-2 min-[900px]:hidden">
      <article v-for="version in versions" :key="version.version" class="rounded-lg border border-line-subtle bg-surface-1 p-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <GovernVersionTag label="Version" :value="version.version" tone="default" />
            <GovernLifecyclePill :state="version.state" />
          </div>
          <span class="font-mono text-[0.6875rem]" :class="checksTone(version)">
            {{ directiveCheckSummary(version).total ? directiveCheckSummary(version).label : "Not configured" }}
          </span>
        </div>
        <p v-if="version.summary" class="mt-2 text-xs leading-5 text-fg-2">{{ version.summary }}</p>
        <p v-else class="mt-2 text-xs text-fg-3"><GovernEmptyValue reason="No change note" /></p>
        <dl class="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[0.6875rem] leading-4">
          <div class="flex items-baseline justify-between gap-2"><dt class="text-fg-3">Author</dt><dd class="truncate text-fg-2">{{ version.author }}</dd></div>
          <div class="flex items-baseline justify-between gap-2"><dt class="text-fg-3">Created</dt><dd class="truncate text-fg-2">{{ formatGovernRelative(version.createdAt) }}</dd></div>
          <div class="col-span-2 flex items-baseline justify-between gap-2"><dt class="text-fg-3">Live window</dt><dd class="truncate text-fg-2">{{ liveWindow(version) }}</dd></div>
          <div class="col-span-2 flex items-center justify-between gap-2"><dt class="text-fg-3">Digest</dt><dd><GovernHashTag :hash="version.hash" label="digest" /></dd></div>
        </dl>
        <div class="mt-2 flex items-center gap-2 border-t border-line-subtle pt-2">
          <button
            type="button"
            class="ix-button-secondary h-7 px-2 text-[0.6875rem]"
            :disabled="!previous(version)"
            @click="compare(version)"
          >
            <ArrowLeftRight :size="11" :stroke-width="1.9" aria-hidden="true" />
            Compare
          </button>
          <button type="button" class="ix-button-secondary h-7 px-2 text-[0.6875rem]" @click="emit('audit')">
            <ScrollText :size="11" :stroke-width="1.9" aria-hidden="true" />
            Audit
          </button>
        </div>
      </article>
    </div>
  </div>
</template>
