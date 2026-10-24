<script setup lang="ts">
import { formatDate, formatNumber, formatPercent, latestHnsw, latestProxy, latestWrite } from '~/data/benchmarks'

const metrics = [
  {
    label: 'Local proxy p99',
    value: `${formatNumber(latestProxy.k6.p99_ms, 2)} ms`,
    scope: 'k6 fast profile · mean gate, not a p99 SLO',
    date: formatDate(latestProxy.timestamp),
  },
  {
    label: 'HNSW recall@10',
    value: formatPercent(latestHnsw.mean_recall_at_10),
    scope: `local corpus · p95 ${formatNumber(latestHnsw.results[1]?.latency_ms_p95, 1)} ms`,
    date: formatDate(latestHnsw.timestamp),
  },
  {
    label: 'Write pipeline p95',
    value: `${formatNumber(latestWrite.metrics.latency_ms_p95, 1)} ms`,
    scope: '40 local iterations',
    date: formatDate(latestWrite.timestamp),
  },
]
</script>

<template>
  <div class="evidence-panel">
    <div class="evidence-top">
      <span class="evidence-kicker">Local benchmark</span>
      <NuxtLink to="/benchmarks" class="evidence-link">
        All runs
        <LandingGlyph name="arrow-up-right" class="size-3" />
      </NuxtLink>
    </div>

    <dl class="metric-list">
      <div v-for="metric in metrics" :key="metric.label" class="metric">
        <dt>{{ metric.label }}</dt>
        <dd>{{ metric.value }}</dd>
        <div class="metric-meta">
          <span>{{ metric.scope }}</span>
          <span>{{ metric.date }}</span>
        </div>
      </div>
    </dl>

    <p class="claim-note">
      <strong>Not claimed:</strong> production readiness, high availability, a hosted p99 SLO, or
      restore drills. Local numbers keep their scope and date.
    </p>
  </div>
</template>

<style scoped>
.evidence-panel {
  min-width: 0;
}

.evidence-top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1rem;
}

.evidence-kicker {
  font-family: var(--font-mono);
  font-size: 0.64rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--site-muted);
}

.evidence-link {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-family: var(--font-mono);
  font-size: 0.62rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--site-ink);
  transition: color 140ms ease;
}

.evidence-link:hover {
  color: var(--site-signal);
}

.metric-list {
  margin: 1.25rem 0 0;
  border-top: 1px solid var(--site-line);
}

.metric {
  display: grid;
  grid-template-columns: minmax(7rem, 0.7fr) minmax(0, 1fr);
  gap: 0.25rem 1.5rem;
  align-items: baseline;
  padding: 0.95rem 0;
  border-bottom: 1px solid var(--site-line);
}

.metric dt {
  font-size: 0.82rem;
  line-height: 1.4;
  color: var(--site-muted);
}

.metric dd {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 1.5rem;
  font-weight: 500;
  line-height: 1;
  letter-spacing: -0.04em;
  font-variant-numeric: tabular-nums;
  color: var(--site-ink);
}

.metric-meta {
  display: flex;
  grid-column: 2;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.2rem 1rem;
  font-family: var(--font-mono);
  font-size: 0.6rem;
  line-height: 1.5;
  color: var(--site-muted);
}

.claim-note {
  margin: 1.2rem 0 0;
  font-size: 0.8rem;
  line-height: 1.6;
  color: var(--site-muted);
  text-wrap: pretty;
}

.claim-note strong {
  color: var(--site-ink);
  font-weight: 560;
}

@media (max-width: 520px) {
  .metric {
    grid-template-columns: 1fr;
  }

  .metric-meta {
    grid-column: 1;
  }
}
</style>
