<script setup lang="ts">
useHead({
  bodyAttrs: { class: 'landing-page' },
})

useSeoMeta({
  title: 'Memory and context for AI agents',
  description: 'Self-hosted memory and context for AI agents. Tenant-scoped, budgeted, inspectable, and OpenAI-compatible.',
  ogTitle: 'Memory for agents. Control for you.',
  ogDescription: 'The self-hosted boundary between your agent and the model. Tenant-scoped memory, bounded context, and evidence attached to every request.',
  ogType: 'website',
})
</script>

<template>
  <div class="landing">
    <LandingCover />
    <LandingPillars />
    <LandingDropIn />
    <LandingProof />
    <LandingQuickstart />
  </div>
</template>

<style scoped>
.landing {
  overflow: clip;
  background: var(--site-bg);
}
</style>
