<script setup lang="ts">
const route = useRoute()

const nav = [
  { label: 'Docs', to: '/docs' },
  { label: 'Benchmarks', to: '/benchmarks' },
  { label: 'Releases', to: '/releases' },
  { label: 'Blog', to: '/blog' },
]

const isActive = (to: string) => route.path === to || route.path.startsWith(`${to}/`)
</script>

<template>
  <UHeader
    :ui="{ center: 'flex-1 justify-center', left: 'min-w-0', right: 'gap-1' }"
    class="docs-header"
  >
    <template #left>
      <NuxtLink to="/" class="docs-brand" aria-label="IBEX Harness home">
        <UColorModeImage
          light="/brand/ibex-mark-light.png"
          dark="/brand/ibex-mark-dark.png"
          alt=""
          class="docs-brand-mark"
        />
        <span class="docs-brand-word">IBEX Harness</span>
      </NuxtLink>
    </template>

    <nav class="docs-nav" aria-label="Primary navigation">
      <NuxtLink
        v-for="item in nav"
        :key="item.to"
        :to="item.to"
        class="docs-nav-link"
        :class="{ 'is-active': isActive(item.to) }"
      >
        {{ item.label }}
      </NuxtLink>
    </nav>

    <template #right>
      <UContentSearchButton
        class="docs-search"
        label="Search"
        :collapsed="false"
        variant="outline"
        :kbds="['meta', 'k']"
        :ui="{
          base: 'h-8 w-[10rem] justify-start rounded-none border-[var(--site-line)] bg-transparent px-2.5 font-mono text-[0.62rem] uppercase tracking-[0.1em] text-[var(--site-muted)] hover:border-[var(--site-line-strong)] hover:bg-[var(--site-surface)] hover:text-[var(--site-ink)]',
        }"
      />

      <NuxtLink
        to="/docs/architecture/status-and-evidence"
        class="docs-status"
        title="G0 is provisional. Read the status ledger."
      >
        <span class="docs-status-dot" aria-hidden="true" />
        <span class="docs-status-id">G0</span>
        <span class="docs-status-sep">·</span>
        <span>Provisional</span>
      </NuxtLink>

      <UButton
        to="https://github.com/Rick1330/ibex-harness"
        target="_blank"
        color="neutral"
        variant="ghost"
        icon="i-simple-icons-github"
        aria-label="IBEX Harness on GitHub"
        class="docs-icon-button"
      />
      <UColorModeButton class="docs-icon-button" />
    </template>

    <template #body>
      <div class="site-mobile-nav">
        <NuxtLink v-for="item in nav" :key="item.to" :to="item.to">
          <span>{{ item.label }}</span>
          <UIcon name="i-lucide-arrow-up-right" class="size-4 text-[var(--site-muted)]" />
        </NuxtLink>

        <div class="docs-mobile-tools">
          <UContentSearchButton class="min-w-0 flex-1" label="Search" :collapsed="false" variant="outline" />
        </div>

        <NuxtLink to="/docs/architecture/status-and-evidence" class="docs-mobile-status">
          <span class="docs-status-dot" aria-hidden="true" />
          G0 · Provisional
          <UIcon name="i-lucide-arrow-up-right" class="size-3.5" />
        </NuxtLink>

        <NuxtLink to="/docs/getting-started/quickstart" class="docs-mobile-cta">
          Quickstart
          <UIcon name="i-lucide-arrow-right" class="size-4" />
        </NuxtLink>
      </div>
    </template>
  </UHeader>
</template>

<style>
.docs-header {
  border-bottom: 1px solid var(--site-line);
  background: var(--site-bg);
}

.docs-brand {
  display: inline-flex;
  align-items: center;
  gap: 0.65rem;
  min-width: 0;
}

.docs-brand .docs-brand-mark {
  width: 1.45rem;
  height: 1.45rem;
  flex: none;
  object-fit: contain;
}

.docs-brand-word {
  overflow: hidden;
  font-family: var(--font-mono);
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.docs-nav {
  display: none;
  align-items: center;
  gap: 0.15rem;
}

.docs-nav-link {
  padding: 0.42rem 0.72rem;
  font-family: var(--font-mono);
  font-size: 0.62rem;
  font-weight: 500;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--site-muted);
  transition: background-color 140ms ease, color 140ms ease;
}

.docs-nav-link:hover {
  background: var(--site-surface);
  color: var(--site-ink);
}

.docs-nav-link.is-active {
  background: var(--site-ink);
  color: var(--site-bg);
}

.docs-search {
  display: none;
}

[data-slot="content"] .docs-search,
[data-slot="content"] .docs-status {
  display: none;
}

.docs-status {
  display: none;
  align-items: center;
  gap: 0.4rem;
  height: 1.9rem;
  padding-inline: 0.55rem;
  border: 1px solid color-mix(in srgb, var(--site-signal) 34%, var(--site-line));
  background: color-mix(in srgb, var(--site-signal) 7%, transparent);
  font-family: var(--font-mono);
  font-size: 0.55rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--site-muted);
  transition: border-color 140ms ease, color 140ms ease;
}

.docs-status:hover {
  border-color: var(--site-signal);
  color: var(--site-ink);
}

.docs-status-dot {
  width: 0.35rem;
  height: 0.35rem;
  flex: none;
  border-radius: 999px;
  background: var(--site-signal);
}

.docs-status-id {
  color: var(--site-ink);
}

.docs-status-sep {
  color: var(--site-line-strong);
}

.docs-header .docs-icon-button {
  border-radius: 0;
}

.docs-mobile-tools {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.85rem;
}

.docs-mobile-status {
  display: inline-flex !important;
  align-items: center;
  justify-content: flex-start !important;
  gap: 0.45rem;
  color: var(--site-muted);
}

.docs-mobile-cta {
  margin-top: 0.35rem;
  border: 1px solid var(--site-ink) !important;
  background: var(--site-ink);
  color: var(--site-bg) !important;
  padding-inline: 0.8rem !important;
}

@media (min-width: 640px) {
  .docs-status {
    display: inline-flex;
  }
}

@media (min-width: 1024px) {
  .docs-nav {
    display: flex;
  }
}

@media (min-width: 1280px) {
  .docs-header .docs-search {
    display: inline-flex;
  }
}

body.landing-page .docs-header {
  border-bottom-color: rgb(10 11 12 / 0.2);
  background: var(--site-landing-field);
  color: var(--site-landing-field-ink);
  backdrop-filter: none;
}

body.landing-page .docs-brand-mark {
  filter: brightness(0);
}

body.landing-page .docs-brand-word,
body.landing-page .docs-nav-link,
body.landing-page .docs-icon-button {
  color: var(--site-landing-field-ink);
}

body.landing-page .docs-nav-link {
  color: rgb(10 11 12 / 0.66);
}

body.landing-page .docs-nav-link:hover {
  background: rgb(10 11 12 / 0.08);
  color: var(--site-landing-field-ink);
}

body.landing-page .docs-nav-link.is-active {
  background: var(--site-landing-field-ink);
  color: var(--site-landing-field);
}

body.landing-page .docs-search {
  border-color: rgb(10 11 12 / 0.26) !important;
  background: transparent !important;
  color: rgb(10 11 12 / 0.66) !important;
}

body.landing-page .docs-search:hover {
  border-color: var(--site-landing-field-ink) !important;
  background: rgb(10 11 12 / 0.06) !important;
  color: var(--site-landing-field-ink) !important;
}

body.landing-page .docs-search kbd {
  background: rgb(10 11 12 / 0.08) !important;
  box-shadow: inset 0 0 0 1px rgb(10 11 12 / 0.16);
  color: var(--site-landing-field-ink) !important;
}

body.landing-page .docs-status {
  border-color: rgb(10 11 12 / 0.24);
  background: transparent;
  color: rgb(10 11 12 / 0.66);
}

body.landing-page .docs-status:hover {
  border-color: var(--site-landing-field-ink);
  color: var(--site-landing-field-ink);
}

body.landing-page .docs-status-dot {
  background: var(--site-landing-field-ink);
}

body.landing-page .docs-status-id {
  color: var(--site-landing-field-ink);
}

body.landing-page .docs-status-sep {
  color: rgb(10 11 12 / 0.35);
}

body.landing-page .docs-icon-button:hover {
  background: rgb(10 11 12 / 0.08) !important;
  color: var(--site-landing-field-ink) !important;
}

body.landing-page .docs-header [data-slot="toggle"],
body.landing-page [data-slot="content"][role="dialog"]:has(.site-mobile-nav) [data-slot="toggle"] {
  color: var(--site-landing-field-ink) !important;
}

body.landing-page [data-slot="content"][role="dialog"]:has(.site-mobile-nav) {
  --ui-border: rgb(10 11 12 / 0.16);
  --ui-text: var(--site-landing-field-ink);
  --ui-text-muted: rgb(10 11 12 / 0.62);
  --site-ink: var(--site-landing-field-ink);
  --site-muted: rgb(10 11 12 / 0.62);
  --site-line: rgb(10 11 12 / 0.16);
  --site-line-strong: rgb(10 11 12 / 0.3);
  --site-surface: rgb(255 255 255 / 0.5);
  --site-surface-strong: #fff;
  border-color: rgb(10 11 12 / 0.16);
  background: var(--site-landing-field);
  color: var(--site-landing-field-ink);
}

body.landing-page [data-slot="content"][role="dialog"]:has(.site-mobile-nav) .site-mobile-nav a {
  border-color: rgb(10 11 12 / 0.16);
  color: var(--site-landing-field-ink);
}

body.landing-page .docs-header [data-slot="toggle"]:hover,
body.landing-page [data-slot="content"][role="dialog"]:has(.site-mobile-nav) [data-slot="toggle"]:hover {
  background: rgb(10 11 12 / 0.08) !important;
}

body.landing-page [data-slot="content"][role="dialog"]:has(.site-mobile-nav) .docs-mobile-tools button {
  background: rgb(255 255 255 / 0.55) !important;
  color: var(--site-landing-field-ink) !important;
  box-shadow: inset 0 0 0 1px rgb(10 11 12 / 0.2) !important;
}

body.landing-page [data-slot="content"][role="dialog"]:has(.site-mobile-nav) .docs-mobile-tools button:hover {
  background: rgb(255 255 255 / 0.82) !important;
}

body.landing-page [data-slot="content"][role="dialog"]:has(.site-mobile-nav) .docs-mobile-cta {
  border-color: var(--site-landing-field-ink) !important;
  background: var(--site-landing-field-ink) !important;
  color: var(--site-landing-field) !important;
}
</style>
