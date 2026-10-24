<template>
  <section id="proof" class="proof" aria-labelledby="proof-title">
    <div class="site-shell">
      <div class="proof-head">
        <div>
          <p class="section-label">03 / Evidence</p>
          <h2 id="proof-title">What works today. What we don’t claim.</h2>
        </div>
        <div class="proof-intro">
          <p>
            IBEX is G0 and provisional. Capabilities and benchmark numbers are published with a
            status, a scope, and a date, so you can tell the difference between a working seam and
            a finished guarantee.
          </p>
          <div class="proof-chips" aria-label="Evidence rules">
            <span>Local evidence</span>
            <span>Scope kept</span>
            <span>No hosted claim</span>
          </div>
        </div>
      </div>

      <div class="proof-frame">
        <div class="proof-frame-bar">
          <span class="proof-frame-title">
            <span class="proof-frame-dot" aria-hidden="true" />
            Status and benchmark ledger
          </span>
          <span>Every number keeps its date</span>
        </div>

        <div class="proof-grid">
          <div class="proof-cell">
            <LandingCapabilityLedger />
          </div>
          <div class="proof-cell">
            <LandingEvidenceLedger />
          </div>
        </div>

        <div class="proof-frame-foot">
          <span>IMPLEMENTED · PROVISIONAL · PROPOSED · DEFERRED · UNKNOWN</span>
          <NuxtLink to="/docs/architecture/status-and-evidence">
            Read the full ledger
            <LandingGlyph name="arrow-up-right" class="size-3" />
          </NuxtLink>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.proof {
  padding: clamp(4.75rem, 8vw, 7.5rem) 0;
  border-top: 1px solid var(--site-line);
}

.proof-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(19rem, 0.55fr);
  gap: 2rem 5rem;
  align-items: end;
}

.proof-head h2 {
  max-width: 15ch;
  margin: 0;
  font-size: clamp(2.5rem, 4.3vw, 4.2rem);
  font-weight: 560;
  line-height: 0.94;
  letter-spacing: -0.06em;
}

.proof-intro p {
  margin: 0;
  font-size: 0.96rem;
  line-height: 1.7;
  color: var(--site-muted);
  text-wrap: pretty;
}

.proof-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 1.15rem;
}

.proof-chips span {
  padding: 0.22rem 0.45rem;
  border: 1px solid var(--site-line);
  font-family: var(--font-mono);
  font-size: 0.53rem;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--site-muted);
}

.proof-frame {
  margin-top: clamp(2.5rem, 4.5vw, 4rem);
  border: 1px solid var(--site-line-strong);
  background: var(--site-surface);
}

.proof-frame-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1.5rem;
  min-height: 2.9rem;
  padding: 0.6rem 1.25rem;
  border-bottom: 1px solid var(--site-line);
  font-family: var(--font-mono);
  font-size: 0.55rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--site-muted);
}

.proof-frame-title {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  color: var(--site-ink);
}

.proof-frame-dot {
  width: 0.38rem;
  height: 0.38rem;
  border-radius: 999px;
  background: var(--site-signal);
}

.proof-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
}

.proof-cell {
  min-width: 0;
  padding: clamp(1.25rem, 2.5vw, 2rem);
}

.proof-cell + .proof-cell {
  border-left: 1px solid var(--site-line);
}

.proof-frame-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1.5rem;
  padding: 0.7rem 1.25rem;
  border-top: 1px solid var(--site-line);
  background: var(--site-bg);
  font-family: var(--font-mono);
  font-size: 0.53rem;
  letter-spacing: 0.06em;
  color: var(--site-muted);
}

.proof-frame-foot a {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  color: var(--site-ink);
  transition: color 140ms ease;
}

.proof-frame-foot a:hover {
  color: var(--site-signal);
}

@media (max-width: 1024px) {
  .proof-head {
    grid-template-columns: 1fr;
    gap: 1.5rem;
  }

  .proof-head h2 {
    max-width: 17ch;
  }

  .proof-intro {
    max-width: 36rem;
  }
}

@media (max-width: 860px) {
  .proof-grid {
    grid-template-columns: 1fr;
  }

  .proof-cell + .proof-cell {
    border-top: 1px solid var(--site-line);
    border-left: 0;
  }
}

@media (max-width: 680px) {
  .proof {
    padding: 4.25rem 0;
  }

  .proof-head h2 {
    font-size: clamp(2.2rem, 9vw, 3rem);
  }

  .proof-frame-bar,
  .proof-frame-foot {
    padding-inline: 1rem;
  }

  .proof-frame-foot span {
    display: none;
  }
}
</style>
