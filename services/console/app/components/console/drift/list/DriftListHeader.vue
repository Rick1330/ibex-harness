<script setup lang="ts">
import { ref } from "vue"
import { Activity, Gauge } from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"

const about = ref<InstanceType<typeof ConsolePageHeader> | null>(null)

const notes = [
  {
    lead: "A signal compares an agent version to its baseline.",
    body: "The band is the certified tolerance around the baseline. Crossing the threshold opens a signal; the state records what a person decided about it.",
  },
  {
    lead: "Causes are suspects, not verdicts.",
    body: "The console ranks recorded changes in the 72 hours before the first out-of-band point. It never claims a change caused the drift.",
  },
  {
    lead: "Missing evaluations stay missing.",
    body: "A monitor with no recent runs reports No data instead of showing a passing band.",
  },
]

function openAbout(): void {
  about.value?.openAbout()
}

defineExpose({ openAbout })
</script>

<template>
  <ConsolePageHeader
    ref="about"
    title="Drift"
    definition="Where agent behaviour has moved away from its certified baseline, and what changed just before."
    state="illustrative"
    verdict="Every signal, band, and cause on this page is an illustrative fixture. No drift read model is connected to this console."
    contract="operator.drift.alerts.v1 [NEEDS-BACKEND]"
    scope="org_demo_42 · workspace ws_42"
    range="Recorded signals, 21–26 Oct 2026"
    coverage="Preview fixtures · no drift read model connected"
    :notes="notes"
  >
    <template #actions>
      <NuxtLink to="/drift/baselines" class="ix-button-secondary">
        <Gauge :size="13" :stroke-width="1.8" aria-hidden="true" />
        Baselines
      </NuxtLink>
      <NuxtLink to="/drift/monitors" class="ix-button-secondary">
        <Activity :size="13" :stroke-width="1.8" aria-hidden="true" />
        Monitors
      </NuxtLink>
    </template>
  </ConsolePageHeader>
</template>
