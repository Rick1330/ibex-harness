<template>
  <figure class="request-map">
    <div class="map-topline">
      <span>One request, end to end</span>
      <span>No new protocol</span>
    </div>

    <div class="map-body">
      <div class="map-node">
        <span class="map-node-label">Your agent</span>
        <strong class="map-node-title">Normal chat request</strong>
        <span class="map-node-meta">PAT · agent ID</span>
      </div>

      <div class="map-link" aria-hidden="true" />

      <div class="map-core">
        <div class="map-core-head">
          <span class="map-core-brand">IBEX / Harness</span>
          <span class="map-core-state">G0 · Provisional</span>
        </div>

        <ol class="map-steps">
          <li class="map-step">
            <span class="map-step-index">01</span>
            <div>
              <strong>Verify</strong>
              <p>Token to org, agent, and scope. Unknown identity stops here.</p>
            </div>
          </li>
          <li class="map-step">
            <span class="map-step-index">02</span>
            <div>
              <strong>Recall</strong>
              <p>Tenant-scoped memories, filtered before they reach the model.</p>
            </div>
          </li>
          <li class="map-step">
            <span class="map-step-index">03</span>
            <div>
              <strong>Fit</strong>
              <p>Rank, pack, and token-cap the context inside a hard deadline.</p>
            </div>
          </li>
          <li class="map-step">
            <span class="map-step-index">04</span>
            <div>
              <strong>Forward</strong>
              <p>An OpenAI-compatible request, streamed from the provider.</p>
            </div>
          </li>
        </ol>

        <div class="map-core-foot">
          <span class="map-foot-item">
            <span class="map-foot-dot" aria-hidden="true" />
            Trace written after the response
          </span>
          <span class="map-foot-item">Directive-only fallback</span>
        </div>
      </div>

      <div class="map-link" aria-hidden="true" />

      <div class="map-node">
        <span class="map-node-label">The model</span>
        <strong class="map-node-title">Provider endpoint</strong>
        <span class="map-node-meta">Streamed response</span>
      </div>
    </div>

    <figcaption>
      The tenant comes from the token, never the request body. If retrieval misses, the request
      continues with its directive.
    </figcaption>
  </figure>
</template>

<style scoped>
.request-map {
  margin: 0;
}

.map-topline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1.5rem;
  padding-bottom: 0.8rem;
  border-bottom: 1px solid var(--site-line);
  font-family: var(--font-mono);
  font-size: 0.64rem;
  letter-spacing: 0.13em;
  text-transform: uppercase;
  color: var(--site-muted);
}

.map-body {
  display: grid;
  grid-template-columns: 12rem minmax(1.5rem, 0.35fr) minmax(0, 3fr) minmax(1.5rem, 0.35fr) 12rem;
  align-items: center;
  gap: 1rem;
  padding: 1.5rem 0;
}

.map-node {
  display: flex;
  min-height: 8.5rem;
  flex-direction: column;
  justify-content: center;
  gap: 0.35rem;
  padding: 1.15rem;
  border: 1px solid var(--site-line-strong);
  background: var(--site-surface);
}

.map-node-label {
  font-family: var(--font-mono);
  font-size: 0.62rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--site-muted);
}

.map-node-title {
  font-size: 1rem;
  font-weight: 560;
  line-height: 1.25;
  letter-spacing: -0.02em;
}

.map-node-meta {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  line-height: 1.5;
  color: var(--site-muted);
}

.map-link {
  position: relative;
  height: 1px;
  background: var(--site-signal);
}

.map-link::after {
  content: "";
  position: absolute;
  top: -3px;
  right: 0;
  border-block: 4px solid transparent;
  border-left: 6px solid var(--site-signal);
}

.map-core {
  min-width: 0;
  border: 1px solid #2c3134;
  border-left: 3px solid #d8ff4f;
  background: #0b0e0f;
  color: #d5d8d1;
}

.map-core-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.8rem 1.15rem;
  border-bottom: 1px solid rgb(255 255 255 / 0.09);
  font-family: var(--font-mono);
  font-size: 0.6rem;
  letter-spacing: 0.13em;
  text-transform: uppercase;
}

.map-core-brand {
  color: #d8ff4f;
}

.map-core-state {
  color: #7f8984;
}

.map-steps {
  margin: 0;
  padding: 0 1.15rem;
  list-style: none;
}

.map-step {
  display: grid;
  grid-template-columns: 2.4rem minmax(0, 1fr);
  gap: 0.9rem;
  padding: 0.9rem 0;
  border-bottom: 1px solid rgb(255 255 255 / 0.075);
}

.map-step:last-child {
  border-bottom: 0;
}

.map-step-index {
  padding-top: 0.08rem;
  font-family: var(--font-mono);
  font-size: 0.62rem;
  letter-spacing: 0.08em;
  color: #d8ff4f;
}

.map-step strong {
  display: block;
  font-size: 0.95rem;
  font-weight: 560;
  letter-spacing: -0.02em;
  color: #f4f1e8;
}

.map-step p {
  margin: 0.18rem 0 0;
  font-size: 0.85rem;
  line-height: 1.5;
  color: #9aa39d;
  text-wrap: pretty;
}

.map-core-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.45rem 1rem;
  padding: 0.7rem 1.15rem;
  border-top: 1px solid rgb(255 255 255 / 0.09);
  font-family: var(--font-mono);
  font-size: 0.58rem;
  letter-spacing: 0.06em;
  color: #7f8984;
}

.map-foot-item {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.map-foot-dot {
  width: 0.35rem;
  height: 0.35rem;
  border-radius: 999px;
  background: #d8ff4f;
}

.request-map figcaption {
  max-width: 52rem;
  padding-top: 1rem;
  border-top: 1px solid var(--site-line);
  font-size: 0.86rem;
  line-height: 1.6;
  color: var(--site-muted);
}

@media (max-width: 1000px) {
  .map-body {
    grid-template-columns: 9rem minmax(1rem, 0.25fr) minmax(0, 3fr) minmax(1rem, 0.25fr) 9rem;
    gap: 0.65rem;
  }

  .map-node {
    padding: 0.9rem;
  }

  .map-node-title {
    font-size: 0.9rem;
  }

  .map-step p {
    font-size: 0.8rem;
  }
}

@media (max-width: 760px) {
  .map-body {
    grid-template-columns: 1fr;
    gap: 0;
    padding-block: 1.15rem;
  }

  .map-node {
    min-height: 0;
    padding: 1rem;
  }

  .map-link {
    width: 1px;
    height: 1.75rem;
    margin-inline: auto;
    background: var(--site-signal);
  }

  .map-link::after {
    top: auto;
    right: auto;
    bottom: 0;
    left: -3px;
    border: 0;
    border-top: 6px solid var(--site-signal);
    border-inline: 4px solid transparent;
  }

  .map-step {
    padding-block: 0.8rem;
  }

  .map-core {
    margin-block: 0.25rem;
  }
}
</style>
