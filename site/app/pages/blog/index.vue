<script setup lang="ts">
interface BlogPost {
  path: string
  title: string
  description?: string
  excerpt?: string
  date?: string
  readingTime?: string
  tags?: string[]
  historical?: boolean
}

const { data: posts } = await useAsyncData<BlogPost[]>('blog-posts', () => {
  return queryCollection('blog').order('date', 'DESC').all() as Promise<BlogPost[]>
}, { default: () => [] })

const featured = computed(() => posts.value?.[0] ?? null)
const rest = computed(() => posts.value?.slice(1) ?? [])

useSeoMeta({
  title: 'Engineering notes',
  description: 'Technical essays on agent memory, request-path security, context assembly, and evidence-backed systems.',
  ogTitle: 'Engineering notes — IBEX Harness',
  ogDescription: 'How AI agent memory, context budgets, and the proxy request path actually work.',
})

function published(value?: string) {
  if (!value) return ''
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(value))
}
</script>

<template>
  <div class="site-shell py-12 sm:py-16">
    <div class="mx-auto max-w-6xl">
      <header class="mx-auto max-w-3xl text-center">
        <p class="site-kicker justify-center">Engineering notes</p>
        <h1 class="site-display mt-5 text-5xl sm:text-7xl">
          How agent memory actually works.
        </h1>
        <p class="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-[var(--site-muted)]">
          Technical essays on request-path security, memory writes, context budgets, and the evidence behind the claims. Every article points back to the
          <NuxtLink to="/docs/architecture/status-and-evidence" class="site-link">status ledger</NuxtLink>.
        </p>
        <div class="mt-7 flex flex-wrap items-center justify-center gap-x-4 gap-y-2 font-mono text-[0.6rem] uppercase tracking-[0.12em] text-[var(--site-muted)]">
          <span>{{ posts.length }} essays</span>
          <span class="size-1 rounded-full bg-[var(--site-line-strong)]" />
          <span>Long-form</span>
          <span class="size-1 rounded-full bg-[var(--site-line-strong)]" />
          <span>Evidence-linked</span>
        </div>
      </header>

      <NuxtLink
        v-if="featured"
        :to="featured.path"
        class="group mt-14 grid gap-6 lg:grid-cols-[1.08fr_0.92fr] lg:items-stretch"
      >
        <BlogCover
          :post="featured"
          :index="1"
          featured
          class="transition-transform duration-300 group-hover:-translate-y-1"
        />
        <div class="flex flex-col justify-between border-y border-[var(--site-line)] py-5 lg:border-y-0 lg:border-l lg:py-2 lg:pl-9">
          <div>
            <div class="flex flex-wrap items-center gap-3 font-mono text-[0.58rem] uppercase tracking-[0.12em] text-[var(--site-muted)]">
              <span class="text-[var(--site-ink)]">Featured note</span>
              <span>{{ published(featured.date) }}</span>
              <span v-if="featured.readingTime">{{ featured.readingTime }}</span>
            </div>
            <h2 class="mt-5 max-w-xl text-3xl font-semibold tracking-[-0.04em] transition-colors group-hover:text-[var(--site-signal)] sm:text-5xl">
              {{ featured.title }}
            </h2>
            <p class="mt-5 max-w-xl text-sm leading-relaxed text-[var(--site-muted)] sm:text-base">
              {{ featured.excerpt || featured.description }}
            </p>
          </div>
          <div class="mt-8 flex flex-wrap items-center justify-between gap-4 border-t border-[var(--site-line)] pt-4">
            <span class="site-mono text-[0.58rem] uppercase tracking-[0.1em] text-[var(--site-muted)]">
              {{ featured.tags?.join(' / ') }}
            </span>
            <span class="site-mono inline-flex items-center gap-1 text-[0.6rem] uppercase tracking-[0.1em]">
              Read note
              <UIcon name="i-lucide-arrow-up-right" class="size-3 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
            </span>
          </div>
        </div>
      </NuxtLink>

      <div v-if="rest.length" class="mt-14 grid gap-10 sm:grid-cols-2 sm:gap-x-8">
        <NuxtLink
          v-for="(post, index) in rest"
          :key="post.path"
          :to="post.path"
          class="group flex flex-col"
        >
          <BlogCover
            :post="post"
            :index="index + 2"
            class="transition-transform duration-300 group-hover:-translate-y-1"
          />
          <div class="flex flex-1 flex-col border-b border-[var(--site-line)] pb-5 pt-4">
            <div class="flex flex-wrap items-center gap-3 font-mono text-[0.56rem] uppercase tracking-[0.1em] text-[var(--site-muted)]">
              <span>{{ published(post.date) }}</span>
              <span v-if="post.readingTime">{{ post.readingTime }}</span>
            </div>
            <h2 class="mt-3 text-2xl font-semibold tracking-[-0.03em] transition-colors group-hover:text-[var(--site-signal)]">
              {{ post.title }}
            </h2>
            <p class="mt-3 flex-1 text-sm leading-relaxed text-[var(--site-muted)]">
              {{ post.excerpt || post.description }}
            </p>
            <div class="mt-6 flex items-center justify-between gap-3 border-t border-[var(--site-line)] pt-3">
              <span class="site-mono text-[0.55rem] uppercase tracking-[0.1em] text-[var(--site-muted)]">
                {{ post.tags?.join(' / ') }}
              </span>
              <UIcon name="i-lucide-arrow-up-right" class="size-4 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
            </div>
          </div>
        </NuxtLink>
      </div>

      <div class="mx-auto mt-16 max-w-3xl border border-[var(--site-line)] bg-[var(--site-surface)] p-5 sm:p-6">
        <div class="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p class="m-0 font-mono text-[0.6rem] uppercase tracking-[0.12em] text-[var(--site-muted)]">Reading the evidence</p>
            <p class="mt-2 max-w-xl text-sm leading-relaxed text-[var(--site-muted)]">
              Essays explain the design. Capability status, known gaps, and verification evidence are maintained in one place.
            </p>
          </div>
          <NuxtLink to="/docs/architecture/status-and-evidence" class="site-button site-button-ghost">
            Status ledger
            <UIcon name="i-lucide-arrow-right" class="size-4" />
          </NuxtLink>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
@media (hover: hover) and (pointer: fine) {
  .group:hover :deep(.blog-cover-rings) {
    transform: translate(-0.4rem, -0.4rem) scale(1.03);
  }

  .group:hover :deep(.blog-cover-index) {
    transform: translateX(0.2rem);
  }

  .group:hover :deep(.blog-cover-rule) {
    width: clamp(3.5rem, 8vw, 6.5rem);
  }
}

@media (prefers-reduced-motion: reduce) {
  .group :deep(.blog-cover),
  .group :deep(.blog-cover-index),
  .group :deep(.blog-cover-rule),
  .group :deep(.blog-cover-rings) {
    transition: none;
  }

  .group:hover :deep(.blog-cover),
  .group:hover :deep(.blog-cover-index),
  .group:hover :deep(.blog-cover-rings) {
    transform: none;
  }
}
</style>
