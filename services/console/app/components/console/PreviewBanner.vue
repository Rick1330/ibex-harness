<script setup lang="ts">
import { computed } from "vue"
import { surfaceForPath } from "~~/shared/operator/surfaces"

const route = useRoute()

const surface = computed(() => surfaceForPath(route.path))
const visible = computed(() => surface.value?.availability === "preview")
</script>

<template>
  <div
    v-if="visible && surface"
    class="ix-preview-banner"
    role="note"
    aria-label="Illustrative preview"
  >
    <span class="ix-preview-badge">Illustrative preview</span>
    <span class="ix-preview-text">
      <strong>{{ surface.label }}</strong> is a design preview. No live operator data is rendered and no contract is
      claimed.
      <template v-if="surface.tier === 'platform'">
        Platform tier: this surface is not part of the memory/context console.
      </template>
    </span>
  </div>
</template>

<style scoped>
.ix-preview-banner {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  border-bottom: 1px solid color-mix(in srgb, var(--ix-warn) 28%, transparent);
  background: var(--ix-warn-tint);
  padding: 0.5rem 1rem;
  font-size: 0.75rem;
  line-height: 1.125rem;
  color: var(--ix-fg-2);
}

.ix-preview-badge {
  flex: none;
  border: 1px solid color-mix(in srgb, var(--ix-warn) 35%, transparent);
  border-radius: 999px;
  padding: 0 0.5rem;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.5625rem;
  line-height: 1.125rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ix-warn);
}

.ix-preview-text {
  min-width: 0;
}

.ix-preview-text strong {
  font-weight: 600;
  color: var(--ix-fg-1);
}
</style>
