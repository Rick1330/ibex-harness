<template>
  <section class="hero" aria-labelledby="landing-title">
    <div class="hero-field">
      <div class="site-shell">
        <div class="hero-panel">
          <div class="hero-panel-bar">
            <span class="hero-panel-brand">
              <span class="hero-panel-dot" aria-hidden="true" />
              IBEX / boundary
            </span>
            <span class="hero-panel-meta">Open source · MIT</span>
          </div>

          <div class="hero-body">
            <div class="hero-copy">
              <p class="hero-kicker">The boundary between your agent and the model</p>
              <h1 id="landing-title">
                <span>Memory for agents.</span>
                <span>Control for you.</span>
              </h1>
              <p class="hero-lede">
                Tenant-scoped memory, bounded context, and an inspectable trace — self-hosted and
                OpenAI-compatible.
              </p>

              <div class="hero-actions">
                <NuxtLink to="/docs/getting-started/quickstart" class="hero-button hero-button-primary">
                  Start in 5 minutes
                  <LandingGlyph name="arrow-right" class="size-3.5" />
                </NuxtLink>
                <a href="#how-it-works" class="hero-button hero-button-ghost">
                  See the boundary
                  <LandingGlyph name="arrow-down" class="size-3.5" />
                </a>
              </div>
            </div>

            <div class="hero-visual">
              <LandingConsole class="hero-console" />
            </div>
          </div>

          <div class="hero-panel-foot">
            <ul class="hero-proof" aria-label="What IBEX provides">
              <li>
                <LandingGlyph name="check" class="size-3.5" />
                OpenAI-compatible
              </li>
              <li>
                <LandingGlyph name="check" class="size-3.5" />
                Tenant-scoped
              </li>
              <li>
                <LandingGlyph name="check" class="size-3.5" />
                Inspectable traces
              </li>
            </ul>
            <span class="hero-claim">No hosted control plane</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.hero {
  background: var(--site-landing-field);
}

.hero-field {
  padding: clamp(0.75rem, 1.6vw, 1.25rem) 0 clamp(2.5rem, 4.5vw, 4.5rem);
  background: var(--site-landing-field);
}

.hero-panel {
  overflow: hidden;
  border: 1px solid #0a0b0c;
  border-radius: clamp(14px, 1.5vw, 20px);
  background: #0a0b0c;
  color: #f2f2ed;
  box-shadow: 0 36px 90px -58px rgb(10 11 12 / 0.7);
}

.hero-panel-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1rem;
  min-height: 2.8rem;
  padding: 0.55rem clamp(1rem, 2.4vw, 2.4rem);
  border-bottom: 1px solid rgb(242 242 237 / 0.14);
  font-family: var(--font-mono);
  font-size: 0.56rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #92978f;
}

.hero-panel-brand {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  color: #f2f2ed;
}

.hero-panel-dot {
  width: 0.38rem;
  height: 0.38rem;
  border-radius: 999px;
  background: #d8ff4f;
  box-shadow: 0 0 0 4px rgb(216 255 79 / 0.14);
}

.hero-panel-meta {
  color: #92978f;
}

.hero-body {
  display: grid;
  grid-template-columns: minmax(0, 0.88fr) minmax(0, 1.12fr);
  gap: clamp(2rem, 4vw, 4rem);
  align-items: center;
  padding: clamp(2rem, 3.6vw, 3.5rem) clamp(1rem, 2.4vw, 2.4rem);
}

.hero-copy {
  min-width: 0;
}

.hero-kicker {
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  margin: 0;
  font-family: var(--font-mono);
  font-size: 0.58rem;
  font-weight: 600;
  letter-spacing: 0.12em;
  line-height: 1.5;
  text-transform: uppercase;
  color: #d8ff4f;
}

.hero-kicker::before {
  content: "";
  width: 1.2rem;
  height: 1px;
  flex: none;
  background: #d8ff4f;
}

.hero-copy h1 {
  display: flex;
  flex-direction: column;
  margin: clamp(1rem, 1.8vw, 1.5rem) 0 0;
  font-family: var(--font-sans);
  font-size: clamp(3.1rem, 5.1vw, 5.4rem);
  font-weight: 560;
  line-height: 0.87;
  letter-spacing: -0.075em;
  color: #f7f7f2;
}

.hero-copy h1 span {
  display: block;
}

.hero-lede {
  max-width: 30rem;
  margin: 1.25rem 0 0;
  font-size: 0.96rem;
  line-height: 1.6;
  color: #b8bcb4;
  text-wrap: pretty;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: clamp(1.4rem, 2.4vw, 1.9rem);
}

.hero-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.55rem;
  min-height: 2.75rem;
  padding: 0.65rem 0.95rem;
  border: 1px solid transparent;
  border-radius: 7px;
  font-family: var(--font-mono);
  font-size: 0.6rem;
  font-weight: 600;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  transition: background-color 140ms ease, border-color 140ms ease, color 140ms ease, transform 140ms ease;
}

.hero-button:hover {
  transform: translateY(-1px);
}

@media (prefers-reduced-motion: reduce) {
  .hero-button,
  .hero-button:hover {
    transform: none;
    transition: none;
  }
}

.hero-button-primary {
  border-color: #d8ff4f;
  background: #d8ff4f;
  color: #0a0b0c;
}

.hero-button-primary:hover {
  border-color: #f2f2ed;
  background: #f2f2ed;
}

.hero-button-ghost {
  border-color: rgb(242 242 237 / 0.26);
  color: #f2f2ed;
}

.hero-button-ghost:hover {
  border-color: rgb(242 242 237 / 0.55);
  background: rgb(255 255 255 / 0.06);
}

.hero-visual {
  display: flex;
  min-width: 0;
  align-items: center;
}

.hero-console {
  width: 100%;
  --site-bg: #e5e9dd;
  --site-surface: #edf1e5;
  --site-surface-strong: #f5f8ed;
  --site-ink: #090b09;
  --site-muted: #4f5b53;
  --site-line: #c7d0bf;
  --site-line-strong: #a2ae9a;
  --site-signal: #5f8f00;
  --site-signal-ink: #0a0b0c;
  --site-code-bg: #e2e7d9;
}

.hero-panel-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem 1.5rem;
  padding: 0.8rem clamp(1rem, 2.4vw, 2.4rem);
  border-top: 1px solid rgb(242 242 237 / 0.14);
  background: #0d0f10;
  font-family: var(--font-mono);
  font-size: 0.54rem;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: #92978f;
}

.hero-proof {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem 1.1rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.hero-proof li {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}

.hero-proof :deep(svg) {
  color: #d8ff4f;
}

.hero-claim {
  color: #b8bcb4;
}

@media (max-width: 1100px) {
  .hero-body {
    grid-template-columns: minmax(0, 0.82fr) minmax(0, 1.18fr);
    gap: clamp(1.5rem, 3vw, 3rem);
  }

  .hero-copy h1 {
    font-size: clamp(2.8rem, 5vw, 4.1rem);
  }
}

@media (max-width: 960px) {
  .hero-body {
    grid-template-columns: 1fr;
    gap: 2.5rem;
  }

  .hero-copy {
    max-width: 42rem;
  }

  .hero-copy h1 {
    font-size: clamp(2.9rem, 6.4vw, 4.4rem);
  }

  .hero-visual {
    max-width: 48rem;
  }
}

@media (max-width: 680px) {
  .hero-field {
    padding-top: 0.6rem;
    padding-bottom: 2rem;
  }

  .hero-panel-bar {
    min-height: 2.4rem;
    padding-inline: 0.9rem;
    font-size: 0.5rem;
  }

  .hero-body {
    gap: 2rem;
    padding: 1.5rem 0.9rem 1.25rem;
  }

  .hero-copy h1 {
    margin-top: 0.9rem;
    font-size: clamp(2.8rem, 12.6vw, 3.45rem);
    line-height: 0.93;
  }

  .hero-lede {
    font-size: 0.92rem;
  }

  .hero-actions {
    flex-direction: column;
  }

  .hero-button {
    width: 100%;
  }

  .hero-panel-foot {
    gap: 0.55rem 1rem;
    padding: 0.75rem 0.9rem;
    font-size: 0.49rem;
  }

  .hero-proof {
    gap: 0.35rem 0.75rem;
  }

  .hero-claim {
    display: none;
  }
}
</style>
