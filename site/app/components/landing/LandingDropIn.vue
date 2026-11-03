<template>
  <section id="drop-in" class="dropin" aria-labelledby="dropin-title">
    <div class="site-shell">
      <div class="dropin-head">
        <div>
          <p class="section-label">02 / Drop-in</p>
          <h2 id="dropin-title">Keep the request. Change the boundary.</h2>
        </div>
        <div class="dropin-intro">
          <p>
            Point your client at IBEX instead of the provider. The request stays
            OpenAI-compatible; auth, tenant scope, memory, and traces move behind the boundary.
          </p>
          <NuxtLink to="/docs/architecture/request-lifecycle" class="dropin-head-link">
            Request lifecycle
            <LandingGlyph name="arrow-right" class="size-3.5" />
          </NuxtLink>
        </div>
      </div>

      <div class="dropin-stage">
        <div class="dropin-code">
          <LandingCodeTabs />
        </div>

        <aside class="dropin-aside" aria-label="Drop-in details">
          <div class="dropin-aside-head">
            <span>What changes</span>
            <span class="dropin-aside-badge">OpenAI-compatible</span>
          </div>

          <ol class="dropin-steps">
            <li>
              <span class="dropin-step-index">01</span>
              <div>
                <strong>Change the base URL</strong>
                <p>Send the same chat completion to your local IBEX proxy.</p>
              </div>
            </li>
            <li>
              <span class="dropin-step-index">02</span>
              <div>
                <strong>Add the agent header</strong>
                <p><code>X-IBEX-Agent-ID</code> binds the call to a known agent.</p>
              </div>
            </li>
            <li>
              <span class="dropin-step-index">03</span>
              <div>
                <strong>Keep the body unchanged</strong>
                <p>Tenant scope is resolved from the token, not from the request body.</p>
              </div>
            </li>
          </ol>

          <dl class="dropin-specs">
            <div>
              <dt>Endpoint</dt>
              <dd>/v1/chat/completions</dd>
            </div>
            <div>
              <dt>Auth</dt>
              <dd>Bearer &lt;PAT&gt;</dd>
            </div>
            <div>
              <dt>Streaming</dt>
              <dd>SSE forwarded</dd>
            </div>
          </dl>

          <div class="dropin-aside-foot">
            <NuxtLink to="/docs/api-reference/chat-completions">
              API reference
              <LandingGlyph name="arrow-up-right" class="size-3" />
            </NuxtLink>
            <span>No SDK required</span>
          </div>
        </aside>
      </div>
    </div>
  </section>
</template>

<style scoped>
.dropin {
  padding: clamp(4.75rem, 8vw, 7.5rem) 0;
  border-block: 1px solid var(--site-line);
  background: var(--site-surface);
}

.dropin-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(19rem, 0.55fr);
  gap: 2rem 5rem;
  align-items: end;
}

.dropin-head h2 {
  max-width: 14ch;
  margin: 0;
  font-size: clamp(2.5rem, 4.3vw, 4.2rem);
  font-weight: 560;
  line-height: 0.94;
  letter-spacing: -0.06em;
}

.dropin-intro p {
  margin: 0;
  font-size: 0.98rem;
  line-height: 1.7;
  color: var(--site-muted);
  text-wrap: pretty;
}

.dropin-head-link {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  margin-top: 1.15rem;
  font-family: var(--font-mono);
  font-size: 0.6rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--site-ink);
  transition: color 140ms ease;
}

.dropin-head-link:hover {
  color: var(--site-signal);
}

.dropin-stage {
  display: grid;
  grid-template-columns: minmax(0, 1.22fr) minmax(18rem, 0.78fr);
  gap: clamp(2rem, 3.5vw, 3.5rem);
  align-items: stretch;
  margin-top: clamp(2.5rem, 4.5vw, 4rem);
}

.dropin-code {
  display: flex;
  min-width: 0;
  flex-direction: column;
  justify-content: center;
}

.dropin-code :deep(.landing-code) {
  border-left-width: 3px;
  box-shadow: 0 32px 80px -66px rgb(10 11 12 / 0.8);
}

.dropin-aside {
  display: flex;
  min-width: 0;
  flex-direction: column;
  padding: 1.15rem;
  border: 1px solid var(--site-line);
  border-radius: 12px;
  background: var(--site-bg);
}

.dropin-aside-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1rem;
  padding-bottom: 0.8rem;
  border-bottom: 1px solid var(--site-line);
  font-family: var(--font-mono);
  font-size: 0.56rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--site-muted);
}

.dropin-aside-badge {
  color: var(--site-signal);
}

.dropin-steps {
  display: grid;
  gap: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}

.dropin-steps li {
  display: grid;
  grid-template-columns: 2rem minmax(0, 1fr);
  gap: 0.7rem;
  padding: 0.9rem 0;
  border-bottom: 1px solid var(--site-line);
}

.dropin-step-index {
  padding-top: 0.08rem;
  font-family: var(--font-mono);
  font-size: 0.56rem;
  color: var(--site-signal);
}

.dropin-steps strong {
  display: block;
  font-size: 0.88rem;
  font-weight: 560;
  line-height: 1.3;
  letter-spacing: -0.02em;
}

.dropin-steps p {
  margin: 0.28rem 0 0;
  font-size: 0.82rem;
  line-height: 1.55;
  color: var(--site-muted);
  text-wrap: pretty;
}

.dropin-steps code {
  font-family: var(--font-mono);
  font-size: 0.76rem;
  color: var(--site-ink);
}

.dropin-specs {
  margin: 0.85rem 0 0;
  border-top: 1px solid var(--site-line);
}

.dropin-specs > div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.55rem 0;
  border-bottom: 1px solid var(--site-line);
}

.dropin-specs dt,
.dropin-specs dd {
  font-family: var(--font-mono);
  font-size: 0.56rem;
}

.dropin-specs dt {
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--site-muted);
}

.dropin-specs dd {
  margin: 0;
  color: var(--site-ink);
  text-align: right;
  overflow-wrap: anywhere;
}

.dropin-aside-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1rem;
  margin-top: auto;
  padding-top: 1rem;
  font-family: var(--font-mono);
  font-size: 0.55rem;
  letter-spacing: 0.04em;
  color: var(--site-muted);
}

.dropin-aside-foot a {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  color: var(--site-ink);
  transition: color 140ms ease;
}

.dropin-aside-foot a:hover {
  color: var(--site-signal);
}

@media (max-width: 1024px) {
  .dropin-head {
    grid-template-columns: 1fr;
    gap: 1.5rem;
  }

  .dropin-head h2 {
    max-width: 17ch;
  }

  .dropin-intro {
    max-width: 36rem;
  }

  .dropin-stage {
    grid-template-columns: 1fr;
  }

  .dropin-aside {
    max-width: 44rem;
  }
}

@media (max-width: 680px) {
  .dropin {
    padding: 4.25rem 0;
  }

  .dropin-head h2 {
    font-size: clamp(2.2rem, 9vw, 3rem);
  }

  .dropin-aside {
    padding: 1rem;
  }
}
</style>
