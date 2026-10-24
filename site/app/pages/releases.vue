<script setup lang="ts">
import releases from '~/data/releases.json'

useSeoMeta({
  title: 'Releases',
  description: 'Human-readable IBEX Harness release notes generated from CHANGELOG.md.',
  ogTitle: 'IBEX Harness releases',
  ogDescription: 'Release notes for the IBEX Harness platform, with issue and commit receipts attached.',
})

const latest = computed(() => releases[0])
const totalItems = computed(() => releases.reduce((sum, release) => sum + itemCount(release), 0))

const recentCount = computed(() => {
  let count = 0
  let opened = 0

  for (const release of releases) {
    const next = itemCount(release)
    if (opened > 0 && count + next > 40) break
    count += next
    opened += 1
  }

  return opened
})

function itemCount(release: (typeof releases)[number]) {
  return release.sections.reduce((count, section) => count + section.items.length, 0)
}

function releaseId(version: string) {
  return `release-${version.replaceAll('.', '-')}`
}

function formatReleaseDate(value: string) {
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${value}T12:00:00Z`))
}

function openHashRelease() {
  const id = window.location.hash.slice(1)
  if (!id) return

  const target = document.getElementById(id)
  const details = target?.querySelector('details')
  if (details) details.open = true
}

onMounted(() => {
  nextTick(openHashRelease)
  window.addEventListener('hashchange', openHashRelease)
})

onNuxtReady(openHashRelease)

onBeforeUnmount(() => {
  window.removeEventListener('hashchange', openHashRelease)
})
</script>

<template>
  <div class="site-shell py-12 lg:py-16">
    <header class="grid gap-10 lg:grid-cols-[1.15fr_0.85fr] lg:items-end">
      <div>
        <p class="site-kicker mb-5">Now / changelog</p>
        <h1 class="site-display max-w-3xl text-5xl sm:text-7xl">
          Changes, with a receipt.
        </h1>
        <p class="mt-6 max-w-2xl text-base leading-relaxed text-[var(--site-muted)]">
          Human-readable summaries of user-visible changes, security fixes, and migrations. Generated from the repository changelog, with issue and commit links kept attached.
        </p>
      </div>
      <div class="grid grid-cols-2 gap-px overflow-hidden border border-[var(--site-line)] bg-[var(--site-line)] sm:grid-cols-3">
        <div class="bg-[var(--site-surface)] p-4">
          <p class="m-0 text-2xl font-medium tracking-[-0.04em] sm:text-3xl">{{ releases.length }}</p>
          <p class="m-0 mt-1 font-mono text-[0.58rem] uppercase tracking-[0.1em] text-[var(--site-muted)]">releases</p>
        </div>
        <div class="bg-[var(--site-surface)] p-4">
          <p class="m-0 text-2xl font-medium tracking-[-0.04em] sm:text-3xl">{{ totalItems }}</p>
          <p class="m-0 mt-1 font-mono text-[0.58rem] uppercase tracking-[0.1em] text-[var(--site-muted)]">changes</p>
        </div>
        <div class="col-span-2 bg-[var(--site-surface)] p-4 sm:col-span-1">
          <p class="m-0 text-2xl font-medium tracking-[-0.04em] sm:text-3xl">{{ latest ? formatReleaseDate(latest.date).replace(/, \d{4}$/, '') : '—' }}</p>
          <p class="m-0 mt-1 font-mono text-[0.58rem] uppercase tracking-[0.1em] text-[var(--site-muted)]">latest</p>
        </div>
      </div>
    </header>

    <div class="mt-12 flex flex-col gap-4 border-y border-[var(--site-line)] py-3 lg:flex-row lg:items-center lg:justify-between">
      <nav class="flex flex-wrap items-center gap-x-5 gap-y-2" aria-label="Release views">
        <span class="font-mono text-[0.66rem] uppercase tracking-[0.1em] text-[var(--site-ink)]">All releases</span>
        <a href="/releases.xml" class="site-mono text-[0.66rem] uppercase tracking-[0.1em] text-[var(--site-muted)] hover:text-[var(--site-ink)]">RSS</a>
        <a href="https://github.com/Rick1330/ibex-harness/blob/main/CHANGELOG.md" target="_blank" rel="noreferrer" class="site-mono text-[0.66rem] uppercase tracking-[0.1em] text-[var(--site-muted)] hover:text-[var(--site-ink)]">CHANGELOG.md</a>
        <a href="https://github.com/Rick1330/ibex-harness/releases" target="_blank" rel="noreferrer" class="site-mono text-[0.66rem] uppercase tracking-[0.1em] text-[var(--site-muted)] hover:text-[var(--site-ink)]">GitHub releases</a>
      </nav>
      <div class="flex flex-wrap gap-1 lg:justify-end">
        <a
          v-for="release in releases"
          :key="release.version"
          :href="`#${releaseId(release.version)}`"
          class="site-mono border border-[var(--site-line)] px-2 py-1 text-[0.58rem] uppercase tracking-[0.08em] text-[var(--site-muted)] transition-colors hover:border-[var(--site-ink)] hover:text-[var(--site-ink)]"
        >
          {{ release.version }}
        </a>
      </div>
    </div>

    <div class="mt-8">
      <article
        v-for="(release, index) in releases"
        :id="releaseId(release.version)"
        :key="release.version"
        class="scroll-mt-24 border-t border-[var(--site-line)] py-10 first:border-t-0 first:pt-0 lg:grid lg:grid-cols-[9rem_minmax(0,1fr)] lg:gap-14"
      >
        <div class="lg:sticky lg:top-24 lg:self-start">
          <div class="flex items-center gap-2">
            <span class="size-1.5 shrink-0 rounded-full" :class="index === 0 ? 'bg-[var(--site-signal)]' : 'bg-[var(--site-line-strong)]'" />
            <time :datetime="release.date" class="site-mono text-[0.62rem] uppercase tracking-[0.1em] text-[var(--site-muted)]">
              {{ formatReleaseDate(release.date) }}
            </time>
          </div>
          <p class="mt-3 font-mono text-[0.62rem] uppercase tracking-[0.1em] text-[var(--site-muted)]">
            {{ itemCount(release) }} changes
          </p>
          <a :href="release.compareUrl" target="_blank" rel="noreferrer" class="site-mono mt-2 inline-flex items-center gap-1 text-[0.58rem] uppercase tracking-[0.1em] text-[var(--site-muted)] hover:text-[var(--site-ink)]">
            Compare
            <UIcon name="i-lucide-arrow-up-right" class="size-3" />
          </a>
        </div>

        <details :open="index < recentCount" class="group mt-4 min-w-0 lg:mt-0">
          <summary class="flex cursor-pointer list-none items-start justify-between gap-4 [&::-webkit-details-marker]:hidden">
            <div class="min-w-0">
              <div class="flex flex-wrap items-end gap-3">
                <h2 class="site-display m-0 text-4xl sm:text-5xl">v{{ release.version }}</h2>
                <span v-if="index === 0" class="site-tag">latest</span>
              </div>

              <div class="mt-4 flex flex-wrap gap-2">
                <span
                  v-for="section in release.sections"
                  :key="section.title"
                  class="site-tag"
                >
                  {{ section.title }} / {{ section.items.length }}
                </span>
              </div>
            </div>
            <span class="mt-1 grid size-8 shrink-0 place-items-center border border-[var(--site-line)] text-[var(--site-muted)] transition-colors group-hover:border-[var(--site-ink)] group-hover:text-[var(--site-ink)]">
              <UIcon name="i-lucide-chevron-down" class="size-4 transition-transform group-open:rotate-180" />
            </span>
          </summary>

          <div class="mt-8 space-y-8">
            <section v-for="section in release.sections" :key="section.title">
              <div class="flex items-center justify-between gap-3 border-b border-[var(--site-line)] pb-2">
                <h3 class="m-0 font-mono text-[0.62rem] uppercase tracking-[0.12em] text-[var(--site-muted)]">{{ section.title }}</h3>
                <span class="site-index">{{ section.items.length }}</span>
              </div>
              <ul class="m-0 list-none p-0">
                <li
                  v-for="(item, itemIndex) in section.items"
                  :key="itemIndex"
                  class="grid gap-2 border-b border-[var(--site-line)] py-3 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-baseline"
                >
                  <p class="m-0 text-sm leading-relaxed">{{ item.text }}</p>
                  <div class="flex flex-wrap items-center gap-2 sm:justify-end">
                    <a
                      v-if="item.issue"
                      :href="item.issue.url"
                      target="_blank"
                      rel="noreferrer"
                      class="site-mono text-[0.58rem] text-[var(--site-muted)] underline decoration-[var(--site-line-strong)] underline-offset-4 hover:text-[var(--site-ink)]"
                    >
                      #{{ item.issue.number }}
                    </a>
                    <a
                      v-if="item.commit"
                      :href="item.commit.url"
                      target="_blank"
                      rel="noreferrer"
                      class="site-mono text-[0.58rem] text-[var(--site-muted)] underline decoration-[var(--site-line-strong)] underline-offset-4 hover:text-[var(--site-ink)]"
                    >
                      {{ item.commit.short }}
                    </a>
                  </div>
                </li>
              </ul>
            </section>
          </div>
        </details>
      </article>
    </div>
  </div>
</template>
