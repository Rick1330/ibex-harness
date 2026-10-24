<script setup lang="ts">
import { capabilities, statusMeta, type Status } from '~/data/ledger'

interface Feature {
  index: string
  title: string
  detail: string
  status: Status
  href: string
  rows: Array<{ label: string; value: string }>
}

const features: Feature[] = [
  {
    index: '01',
    title: 'Knows who is asking.',
    detail: 'Validates the token and binds the agent to its organization. Tenant scope comes from the credential, never the request body.',
    status: 'IMPLEMENTED',
    href: '/docs/security/authentication',
    rows: [
      { label: 'authorization', value: 'verified' },
      { label: 'org_id', value: 'from token' },
      { label: 'permissions', value: 'enforced' },
    ],
  },
  {
    index: '02',
    title: 'Recalls only their memory.',
    detail: 'Retrieves tenant-scoped memories from PostgreSQL and pgvector, then ranks them without letting another organization’s data into the window.',
    status: 'IMPLEMENTED',
    href: '/docs/memory/overview',
    rows: [
      { label: 'retrieval', value: 'pgvector' },
      { label: 'scope', value: 'org-filtered' },
      { label: 'cache', value: 'Redis hot path' },
    ],
  },
  {
    index: '03',
    title: 'Fits context to budget.',
    detail: 'Calculates a token budget, packs the directive and ranked memories, and degrades to directive-only context when retrieval misses.',
    status: 'PROVISIONAL',
    href: '/docs/context/overview',
    rows: [
      { label: 'budget', value: 'computed' },
      { label: 'ranking', value: 'budget-aware' },
      { label: 'fallback', value: 'directive-only' },
    ],
  },
  {
    index: '04',
    title: 'Routes to the model you chose.',
    detail: 'Keeps the OpenAI-compatible request shape while OpenAI, Anthropic, OpenAI-compatible, and mock adapters sit behind one boundary.',
    status: 'IMPLEMENTED',
    href: '/docs/proxy/provider-adapters',
    rows: [
      { label: 'openai', value: 'native' },
      { label: 'anthropic', value: 'adapter' },
      { label: 'compatible', value: 'adapter' },
    ],
  },
  {
    index: '05',
    title: 'Streams without holding the client.',
    detail: 'Forwards provider SSE, normalizes upstream errors, and keeps trace writes off the critical path. Slow-client soak evidence remains open.',
    status: 'PROVISIONAL',
    href: '/docs/proxy/provider-routing-and-resilience',
    rows: [
      { label: 'stream', value: 'SSE forwarded' },
      { label: 'errors', value: 'normalized' },
      { label: 'trace', value: 'async write' },
    ],
  },
  {
    index: '06',
    title: 'Leaves evidence behind.',
    detail: 'Records the route, token usage, and timing with a scope and date. The relay is default-off; this is local evidence, not a hosted guarantee.',
    status: 'PROVISIONAL',
    href: '/docs/operations/evidence-and-relay',
    rows: [
      { label: 'outbox', value: 'local evidence' },
      { label: 'relay', value: 'default-off' },
      { label: 'claim', value: 'scoped' },
    ],
  },
]

const capabilityCount = capabilities.length
</script>

<template>
  <section id="how-it-works" class="surfaces" aria-labelledby="surfaces-title">
    <div class="site-shell">
      <div class="surfaces-head">
        <div>
          <p class="section-label">01 / The boundary</p>
          <h2 id="surfaces-title">One boundary. Six jobs.</h2>
        </div>
        <div class="surfaces-intro">
          <p>
            Use IBEX when agents need customer context without crossing tenant lines, or when you
            need a bounded, inspectable path to any model.
          </p>
          <div class="surfaces-links">
            <NuxtLink to="/docs/architecture/overview" class="surfaces-link">
              Architecture overview
              <LandingGlyph name="arrow-right" class="size-3.5" />
            </NuxtLink>
            <NuxtLink to="/docs/architecture/status-and-evidence" class="surfaces-link">
              All {{ capabilityCount }} capabilities
              <LandingGlyph name="arrow-up-right" class="size-3.5" />
            </NuxtLink>
          </div>
        </div>
      </div>

      <div class="features-grid">
        <article v-for="feature in features" :key="feature.index" class="feature">
          <div class="feature-top">
            <span class="feature-index">{{ feature.index }}</span>
            <span
              class="site-status"
              :class="`status-${feature.status.toLowerCase()}`"
            >
              {{ statusMeta[feature.status].label }}
            </span>
          </div>

          <h3>{{ feature.title }}</h3>
          <p class="feature-detail">{{ feature.detail }}</p>

          <dl class="feature-rows">
            <div v-for="row in feature.rows" :key="row.label">
              <dt>{{ row.label }}</dt>
              <dd>{{ row.value }}</dd>
            </div>
          </dl>

          <NuxtLink :to="feature.href" class="feature-link">
            Read the contract
            <LandingGlyph name="arrow-up-right" class="size-3" />
          </NuxtLink>
        </article>
      </div>
    </div>
  </section>
</template>

<style scoped>
.surfaces {
  padding: clamp(4.5rem, 7vw, 7rem) 0;
  background: color-mix(in srgb, var(--site-signal) 8%, var(--site-bg));
}

.surfaces-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(19rem, 0.55fr);
  gap: 2rem 5rem;
  align-items: end;
}

.surfaces-head h2 {
  max-width: 14ch;
  margin: 0;
  font-size: clamp(2.5rem, 4.3vw, 4.2rem);
  font-weight: 560;
  line-height: 0.94;
  letter-spacing: -0.06em;
}

.surfaces-intro p {
  margin: 0;
  font-size: 0.98rem;
  line-height: 1.7;
  color: var(--site-muted);
  text-wrap: pretty;
}

.surfaces-links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1.25rem;
  margin-top: 1.15rem;
}

.surfaces-link {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-family: var(--font-mono);
  font-size: 0.6rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--site-ink);
  transition: color 140ms ease;
}

.surfaces-link:hover {
  color: var(--site-signal);
}

.features-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1px;
  margin-top: clamp(2.5rem, 4.5vw, 4rem);
  border: 1px solid var(--site-line);
  background: var(--site-line);
}

.feature {
  display: flex;
  min-width: 0;
  flex-direction: column;
  padding: clamp(1.25rem, 2vw, 1.8rem);
  background: var(--site-surface-strong);
  transition: background-color 180ms ease;
}

.feature:hover {
  background: color-mix(in srgb, var(--site-signal) 4%, var(--site-surface-strong));
}

.feature-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.feature-index {
  font-family: var(--font-mono);
  font-size: 0.58rem;
  letter-spacing: 0.12em;
  color: var(--site-signal);
}

.feature h3 {
  max-width: 18ch;
  margin: 1.35rem 0 0;
  font-size: clamp(1.35rem, 1.8vw, 1.7rem);
  font-weight: 560;
  line-height: 1.06;
  letter-spacing: -0.045em;
}

.feature-detail {
  max-width: 29rem;
  margin: 0.8rem 0 0;
  font-size: 0.9rem;
  line-height: 1.62;
  color: var(--site-muted);
  text-wrap: pretty;
}

.feature-rows {
  margin: auto 0 0;
  padding-top: 1.2rem;
}

.feature-rows > div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.52rem 0;
  border-top: 1px solid var(--site-line);
}

.feature-rows > div:last-child {
  border-bottom: 1px solid var(--site-line);
}

.feature-rows dt,
.feature-rows dd {
  font-family: var(--font-mono);
  font-size: 0.56rem;
  letter-spacing: 0.04em;
}

.feature-rows dt {
  color: var(--site-muted);
}

.feature-rows dd {
  margin: 0;
  color: var(--site-ink);
  text-align: right;
}

.feature-link {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  margin-top: 1rem;
  font-family: var(--font-mono);
  font-size: 0.55rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--site-muted);
  transition: color 140ms ease;
}

.feature-link:hover {
  color: var(--site-signal);
}

@media (max-width: 1024px) {
  .surfaces-head {
    grid-template-columns: 1fr;
    gap: 1.5rem;
  }

  .surfaces-head h2 {
    max-width: 17ch;
  }

  .surfaces-intro {
    max-width: 36rem;
  }

  .features-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 680px) {
  .surfaces {
    padding: 4.25rem 0;
  }

  .surfaces-head h2 {
    font-size: clamp(2.2rem, 9vw, 3rem);
  }

  .features-grid {
    grid-template-columns: 1fr;
  }

  .feature h3 {
    max-width: 22ch;
  }
}
</style>
