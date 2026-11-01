<script setup lang="ts">
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import SessionsPreview from "@/components/console/previews/SessionsPreview.vue"

const notes = [
  {
    lead: "A session groups turns, not HTTP requests.",
    body: "One session is the ordered set of turns an agent ran for a single operator question. Turn-level policy and retrieval records join to the session, not to the browser request.",
  },
  {
    lead: "Coverage is reported, not inferred.",
    body: "A session with partial trace coverage says so. The console never fills a missing turn from the sessions around it.",
  },
  {
    lead: "Filters stay in the URL.",
    body: "Search, saved view, environments, outcomes, tier, agent, duration, sort, and hidden columns all survive reload and back/forward.",
  },
]
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">
    <ConsolePageHeader
      title="Sessions"
      definition="What happened across an agent session, turn by turn, and how complete the recorded evidence is."
      state="illustrative"
      verdict="Preview renders 18 illustrative sessions with turn counts, outcomes, coverage, and cost. Session-to-trace joins and turn-level policy records are not connected, so no live session state is claimed."
      contract="operator.sessions.list.v1 + trace joins [NEEDS-BACKEND]"
      scope="org_demo_42 · all agents"
      range="Recorded sessions, 26–30 Oct 2026"
      coverage="0% live · 18 illustrative sessions"
      :notes="notes"
    />
    <SessionsPreview />
  </div>
</template>
