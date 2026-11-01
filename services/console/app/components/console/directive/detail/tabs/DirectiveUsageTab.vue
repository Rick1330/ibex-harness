<script setup lang="ts">
import { computed } from "vue"
import { ChartNoAxesColumn, History } from "@lucide/vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernPendingData from "@/components/console/govern/primitives/GovernPendingData.vue"
import GovernVersionTag from "@/components/console/govern/primitives/GovernVersionTag.vue"
import { directiveLive, type Directive } from "@/lib/directive-preview"
import { formatGovernNumber, formatGovernPercent } from "@/lib/govern-format"

const props = defineProps<{ directive: Directive }>()

const live = computed(() => directiveLive(props.directive))
const sessions = computed(() => props.directive.usage.sessionsByVersion)
const errorRates = computed(() => props.directive.usage.errorRateByVersion)
const hasAnyUsage = computed(() => Boolean(sessions.value?.length || errorRates.value?.length))
</script>

<template>
  <div class="min-w-0 space-y-4">
    <div class="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <section class="min-w-0 rounded-lg border border-line-subtle bg-surface-1 p-4" aria-labelledby="usage-sessions-title">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="usage-sessions-title" class="flex items-center gap-1.5 text-xs font-semibold text-fg-1">
            <ChartNoAxesColumn :size="13" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
            Sessions by version
          </h2>
          <span v-if="sessions?.length" class="font-mono text-[0.6875rem] text-fg-3 tabular-nums">{{ sessions.length }} versions</span>
        </div>

        <div v-if="sessions?.length" class="mt-3">
          <table class="w-full text-xs">
            <thead>
              <tr class="border-b border-line-subtle text-left text-[0.6875rem] text-fg-3">
                <th scope="col" class="py-1.5 font-medium">Version</th>
                <th scope="col" class="py-1.5 text-right font-medium">Sessions</th>
                <th scope="col" class="py-1.5 text-right font-medium">Error rate</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-line-subtle">
              <tr v-for="row in sessions" :key="row.version">
                <td class="py-2"><GovernVersionTag label="Version" :value="row.version" tone="default" /></td>
                <td class="py-2 text-right font-mono tabular-nums text-fg-2">{{ formatGovernNumber(row.sessions) }}</td>
                <td class="py-2 text-right font-mono tabular-nums" :class="row.errorRate === null ? 'text-fg-3' : 'text-fg-2'">
                  {{ row.errorRate === null ? "Not recorded" : formatGovernPercent(row.errorRate) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="mt-3">
          <GovernPendingData
            title="Directive usage"
            contract="operator.directives.usage.v1"
            description="Session and error-rate attribution per directive version is not connected in this console build."
          />
        </div>
      </section>

      <section class="min-w-0 rounded-lg border border-line-subtle bg-surface-1 p-4" aria-labelledby="usage-errors-title">
        <h2 id="usage-errors-title" class="flex items-center gap-1.5 text-xs font-semibold text-fg-1">
          <History :size="13" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
          Error rate vs baseline
        </h2>
        <div v-if="errorRates?.length" class="mt-3">
          <table class="w-full text-xs">
            <thead>
              <tr class="border-b border-line-subtle text-left text-[0.6875rem] text-fg-3">
                <th scope="col" class="py-1.5 font-medium">Version</th>
                <th scope="col" class="py-1.5 text-right font-medium">Rate</th>
                <th scope="col" class="py-1.5 text-right font-medium">Baseline</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-line-subtle">
              <tr v-for="row in errorRates" :key="row.version">
                <td class="py-2"><GovernVersionTag label="Version" :value="row.version" tone="default" /></td>
                <td class="py-2 text-right font-mono tabular-nums text-fg-2">{{ formatGovernPercent(row.errorRate) }}</td>
                <td class="py-2 text-right font-mono tabular-nums text-fg-3">{{ formatGovernPercent(row.baselineErrorRate) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="mt-3">
          <GovernPendingData
            title="Error-rate comparison"
            contract="operator.directives.usage.v1"
            description="A per-version error rate needs the session read model. No baseline is substituted."
          />
        </div>
      </section>
    </div>

    <GovernCaveat v-if="!hasAnyUsage" tone="info" title="Why this tab is empty">
      Usage attribution joins sessions back to the directive version that served them. That join is not part of the
      versions contract, so this console shows a pending state instead of a derived or estimated number.
      <span v-if="live" class="block pt-1">The live version is <span class="font-mono">{{ live.version }}</span>; it stays live until a candidate passes the promotion gate.</span>
    </GovernCaveat>
  </div>
</template>
