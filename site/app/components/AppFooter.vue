<script setup lang="ts">
const year = new Date().getFullYear()
</script>

<template>
  <footer class="app-footer">
    <div class="app-footer-shell">
      <div class="app-footer-grid">
        <div class="app-footer-brand">
          <NuxtLink to="/" class="app-footer-brand-link" aria-label="IBEX Harness home">
            <UColorModeImage
              light="/brand/ibex-mark-light.png"
              dark="/brand/ibex-mark-dark.png"
              alt=""
              class="app-footer-mark"
            />
            <span>IBEX Harness</span>
          </NuxtLink>

          <p class="app-footer-tagline">
            The self-hosted memory and context layer for AI agents.
          </p>

          <NuxtLink to="/docs/architecture/status-and-evidence" class="app-footer-status">
            <span aria-hidden="true" />
            G0 · Provisional
            <UIcon name="i-lucide-arrow-up-right" class="size-3" />
          </NuxtLink>
        </div>

        <nav aria-label="Product">
          <p class="app-footer-heading">Product</p>
          <NuxtLink to="/docs/getting-started/quickstart" class="app-footer-link">Quickstart</NuxtLink>
          <NuxtLink to="/docs/architecture/overview" class="app-footer-link">Architecture</NuxtLink>
          <NuxtLink to="/docs/api-reference/chat-completions" class="app-footer-link">API reference</NuxtLink>
          <NuxtLink to="/docs/architecture/status-and-evidence" class="app-footer-link">Status and evidence</NuxtLink>
        </nav>

        <nav aria-label="Evidence">
          <p class="app-footer-heading">Evidence</p>
          <NuxtLink to="/benchmarks" class="app-footer-link">Benchmarks</NuxtLink>
          <NuxtLink to="/releases" class="app-footer-link">Releases</NuxtLink>
          <NuxtLink to="/blog" class="app-footer-link">Engineering blog</NuxtLink>
        </nav>

        <nav aria-label="Source">
          <p class="app-footer-heading">Source</p>
          <a href="https://github.com/Rick1330/ibex-harness" target="_blank" rel="noreferrer" class="app-footer-link">GitHub</a>
          <a href="https://github.com/Rick1330/ibex-harness/blob/main/LICENSE" target="_blank" rel="noreferrer" class="app-footer-link">MIT license</a>
          <a href="https://github.com/Rick1330/ibex-harness/tree/main/engineering/adr" target="_blank" rel="noreferrer" class="app-footer-link">Decision records</a>
          <a href="/llms.txt" class="app-footer-link">llms.txt</a>
        </nav>
      </div>

      <div class="app-footer-bottom">
        <p>© {{ year }} IBEX Harness · MIT</p>
        <p>No production claim without evidence.</p>
      </div>
    </div>
  </footer>
</template>

<style scoped>
.app-footer {
  border-top: 1px solid var(--site-line);
  background: var(--site-bg);
}

.app-footer-shell {
  width: min(100% - 2rem, 84rem);
  margin-inline: auto;
}

.app-footer-grid {
  display: grid;
  gap: 2.5rem;
  padding: 3.75rem 0 2.75rem;
}

.app-footer-brand {
  max-width: 21rem;
}

.app-footer-brand-link {
  display: inline-flex;
  align-items: center;
  gap: 0.65rem;
  font-family: var(--font-mono);
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.app-footer-brand-link :deep(.app-footer-mark) {
  width: 1.45rem;
  height: 1.45rem;
  object-fit: contain;
}

.app-footer-tagline {
  margin: 1rem 0 0;
  font-size: 0.84rem;
  line-height: 1.65;
  color: var(--site-muted);
}

.app-footer-status {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  margin-top: 1.15rem;
  font-family: var(--font-mono);
  font-size: 0.58rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--site-muted);
  transition: color 140ms ease;
}

.app-footer-status:hover {
  color: var(--site-ink);
}

.app-footer-status span {
  width: 0.35rem;
  height: 0.35rem;
  border-radius: 999px;
  background: var(--site-signal);
}

.app-footer-heading {
  margin: 0 0 0.9rem;
  font-family: var(--font-mono);
  font-size: 0.6rem;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--site-muted);
}

.app-footer-link {
  display: block;
  padding: 0.26rem 0;
  font-size: 0.82rem;
  color: var(--site-ink);
  transition: color 140ms ease;
}

.app-footer-link:hover {
  color: var(--site-signal);
}

.app-footer-bottom {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 1rem 0 1.5rem;
  border-top: 1px solid var(--site-line);
  font-family: var(--font-mono);
  font-size: 0.58rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--site-muted);
}

.app-footer-bottom p {
  margin: 0;
}

@media (min-width: 768px) {
  .app-footer-grid {
    grid-template-columns: 1.65fr repeat(3, 1fr);
  }

  .app-footer-bottom {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
  }
}
</style>
