<script setup lang="ts">
import { capabilities } from '~/data/ledger'

const total = capabilities.length
const core = capabilities.filter(capability =>
  capability.status === 'IMPLEMENTED' || capability.status === 'PROVISIONAL',
).length

const count = (status: string) => capabilities.filter(capability => capability.status === status).length
const implemented = count('IMPLEMENTED')
const provisional = count('PROVISIONAL')
const proposed = count('PROPOSED')
const deferred = count('DEFERRED')

const groups = [
  { key: 'implemented', label: 'Implemented', count: implemented },
  { key: 'provisional', label: 'Provisional', count: provisional },
  { key: 'proposed', label: 'Proposed', count: proposed },
  { key: 'deferred', label: 'Deferred', count: deferred },
]
</script>

<template>
  <div class="status-panel">
    <div class="status-top">
      <span class="status-kicker">Capability status</span>
      <span class="status-badge">
        <span aria-hidden="true" />
        Local evidence
      </span>
    </div>

    <p class="status-heading">
      <strong>{{ implemented }} of {{ total }}</strong>
      capabilities implemented locally.
    </p>

    <p class="status-copy">
      {{ core }} are implemented or have a running seam. Every status is public, and every claim
      links back to its evidence. Hosted, HA, and production readiness are not claimed.
    </p>

    <div
      class="status-bar"
      aria-hidden="true"
    >
      <span
        v-for="index in implemented"
        :key="`implemented-${index}`"
        class="status-cell is-implemented"
      />
      <span
        v-for="index in provisional"
        :key="`provisional-${index}`"
        class="status-cell is-provisional"
      />
      <span
        v-for="index in proposed"
        :key="`proposed-${index}`"
        class="status-cell is-proposed"
      />
      <span
        v-for="index in deferred"
        :key="`deferred-${index}`"
        class="status-cell is-deferred"
      />
    </div>

    <ul class="status-legend">
      <li v-for="group in groups" :key="group.key">
        <span class="legend-mark" :class="`is-${group.key}`" aria-hidden="true" />
        <span class="legend-label">{{ group.label }}</span>
        <span class="legend-count">{{ group.count }}</span>
      </li>
    </ul>

    <NuxtLink to="/docs/architecture/status-and-evidence" class="status-link">
      See the full status ledger
      <LandingGlyph name="arrow-right" class="size-3.5" />
    </NuxtLink>
  </div>
</template>

<style scoped>
.status-panel {
  min-width: 0;
}

.status-top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.65rem 1rem;
}

.status-kicker {
  font-family: var(--font-mono);
  font-size: 0.64rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--site-muted);
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-family: var(--font-mono);
  font-size: 0.62rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--site-ink);
}

.status-badge > span {
  width: 0.38rem;
  height: 0.38rem;
  border-radius: 999px;
  background: var(--site-signal);
}

.status-heading {
  max-width: 15ch;
  margin: 1.25rem 0 0;
  font-size: clamp(1.7rem, 2.6vw, 2.3rem);
  font-weight: 560;
  line-height: 1.02;
  letter-spacing: -0.045em;
}

.status-heading strong {
  color: var(--site-signal);
  font-weight: 560;
}

.status-copy {
  max-width: 33rem;
  margin: 0.9rem 0 0;
  font-size: 0.9rem;
  line-height: 1.65;
  color: var(--site-muted);
  text-wrap: pretty;
}

.status-bar {
  display: flex;
  gap: 0.2rem;
  margin-top: 1.5rem;
}

.status-cell {
  height: 0.75rem;
  flex: 1 1 0;
  min-width: 0;
}

.is-implemented {
  background: var(--site-signal);
}

.is-provisional {
  background: var(--site-ink);
}

.is-proposed {
  border: 1px solid var(--site-muted);
  background: transparent;
}

.is-deferred {
  border: 1px dashed var(--site-line-strong);
  background: transparent;
}

.status-legend {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.6rem 1.5rem;
  margin: 1rem 0 0;
  padding: 0;
  list-style: none;
}

.status-legend li {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.78rem;
}

.legend-mark {
  width: 0.5rem;
  height: 0.5rem;
  flex: none;
}

.legend-mark.is-implemented {
  border-radius: 999px;
}

.legend-label {
  color: var(--site-ink);
}

.legend-count {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--site-muted);
  font-variant-numeric: tabular-nums;
}

.status-link {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  margin-top: 1.35rem;
  font-family: var(--font-mono);
  font-size: 0.62rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--site-ink);
  transition: color 140ms ease;
}

.status-link:hover {
  color: var(--site-signal);
}

@media (max-width: 640px) {
  .status-legend {
    grid-template-columns: 1fr;
    gap: 0.45rem;
  }

  .status-heading {
    font-size: 1.8rem;
  }
}
</style>
