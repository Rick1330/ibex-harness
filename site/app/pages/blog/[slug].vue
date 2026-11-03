<script setup lang="ts">
interface BlogPost {
  path: string
  title: string
  description?: string
  excerpt?: string
  date?: string
  author?: string
  authorUrl?: string
  readingTime?: string
  tags?: string[]
  historical?: boolean
}

const AUTHOR_GITHUB = 'https://github.com/Rick1330'
const AUTHOR_X = 'https://x.com/Rick_Riener'
const AUTHOR_ROLE = 'Maintainer · IBEX Harness'
const AUTHOR_NAME = 'Elshaday Mengesha'

const route = useRoute()
const { data } = await useAsyncData(`blog-${route.path}`, async () => {
  const all = await queryCollection('blog').order('date', 'DESC').all() as BlogPost[]
  const index = all.findIndex(post => post.path === route.path)
  return { all, index }
}, { default: () => ({ all: [] as BlogPost[], index: -1 }) })

const post = computed(() => data.value.index >= 0 ? data.value.all[data.value.index] : null)
const newer = computed(() => data.value.index > 0 ? data.value.all[data.value.index - 1] : null)
const older = computed(() => data.value.index >= 0 ? data.value.all[data.value.index + 1] ?? null : null)

const site = useSiteConfig()
const shareUrl = computed(() => {
  const base = site.url || 'https://ibexharness.com'
  return new URL(post.value?.path || route.path, base).href
})
const authorName = computed(() => post.value?.author || AUTHOR_NAME)

if (!post.value) {
  throw createError({ statusCode: 404, statusMessage: 'Post not found', fatal: true })
}

useSeoMeta({
  title: post.value.title,
  description: post.value.description || post.value.excerpt,
  ogType: 'article',
})

const published = computed(() => {
  if (!post.value?.date) return ''
  return new Intl.DateTimeFormat('en', { dateStyle: 'long', timeZone: 'UTC' }).format(new Date(post.value.date))
})
</script>

<template>
  <div id="top" class="site-shell py-10 sm:py-16">
    <article v-if="post" class="mx-auto max-w-6xl">
      <NuxtLink to="/blog" class="site-mono inline-flex items-center gap-1.5 text-[0.62rem] uppercase tracking-[0.12em] text-[var(--site-muted)] hover:text-[var(--site-ink)]">
        <UIcon name="i-lucide-arrow-left" class="size-3" />
        All notes
      </NuxtLink>

      <header class="mt-8 max-w-3xl">
        <div class="flex flex-wrap items-center gap-3 font-mono text-[0.58rem] uppercase tracking-[0.12em] text-[var(--site-muted)]">
          <time :datetime="post.date">{{ published }}</time>
          <span class="size-1 rounded-full bg-[var(--site-line-strong)]" />
          <span v-if="post.readingTime">{{ post.readingTime }}</span>
          <span class="size-1 rounded-full bg-[var(--site-line-strong)]" />
          <span>Engineering note</span>
        </div>
        <h1 class="site-display mt-4 text-4xl sm:text-6xl">
          {{ post.title }}
        </h1>
        <p v-if="post.excerpt" class="mt-5 text-lg leading-relaxed text-[var(--site-muted)]">
          {{ post.excerpt }}
        </p>
        <div v-if="post.tags?.length" class="mt-6 flex flex-wrap items-center gap-3 border-t border-[var(--site-line)] pt-4 text-xs text-[var(--site-muted)]">
          <span v-for="tag in post.tags" :key="tag" class="site-mono border border-[var(--site-line)] px-2 py-0.5">
            {{ tag }}
          </span>
        </div>
      </header>

      <div class="mt-10 grid gap-8 lg:grid-cols-[15rem_minmax(0,1fr)] lg:items-start lg:gap-14">
        <BlogAuthorCard
          class="lg:sticky lg:top-24"
          :name="authorName"
          :role="AUTHOR_ROLE"
          :github-url="AUTHOR_GITHUB"
          :x-url="AUTHOR_X"
          :share-url="shareUrl"
        />

        <div class="min-w-0 max-w-3xl">
          <BlogCover
            :post="post"
            :index="data.index + 1"
            featured
          />

          <Callout
            v-if="post.historical"
            type="note"
            title="Historical post"
            to="/docs/architecture/status-and-evidence"
            class="mt-8"
          >
            This post reflects the project at the time it was written. Current capability claims are maintained in the status ledger, not here.
          </Callout>

          <div class="site-prose mt-10">
            <ContentRenderer :value="post" />
          </div>

          <footer class="mt-14 border-t border-[var(--site-line)] pt-6">
            <div class="flex flex-wrap items-center justify-between gap-4">
              <div class="flex flex-wrap gap-2">
                <span v-for="tag in post.tags" :key="tag" class="site-tag">{{ tag }}</span>
              </div>
              <a href="#top" class="site-mono inline-flex items-center gap-1 text-[0.6rem] uppercase tracking-[0.1em] text-[var(--site-muted)] hover:text-[var(--site-ink)]">
                Back to top
                <UIcon name="i-lucide-arrow-up" class="size-3" />
              </a>
            </div>
          </footer>

          <nav v-if="newer || older" class="mt-10 grid gap-px border border-[var(--site-line)] bg-[var(--site-line)] sm:grid-cols-2" aria-label="More posts">
            <NuxtLink
              v-if="newer"
              :to="newer.path"
              class="group bg-[var(--site-bg)] p-5 transition-colors hover:bg-[var(--site-surface)]"
            >
              <p class="m-0 font-mono text-[0.56rem] uppercase tracking-[0.12em] text-[var(--site-muted)]">Newer note</p>
              <p class="m-0 mt-2 text-sm font-medium transition-colors group-hover:text-[var(--site-signal)]">{{ newer.title }}</p>
            </NuxtLink>
            <NuxtLink
              v-if="older"
              :to="older.path"
              class="group bg-[var(--site-bg)] p-5 transition-colors hover:bg-[var(--site-surface)] sm:text-right"
            >
              <p class="m-0 font-mono text-[0.56rem] uppercase tracking-[0.12em] text-[var(--site-muted)]">Older note</p>
              <p class="m-0 mt-2 text-sm font-medium transition-colors group-hover:text-[var(--site-signal)]">{{ older.title }}</p>
            </NuxtLink>
          </nav>
        </div>
      </div>
    </article>
  </div>
</template>
