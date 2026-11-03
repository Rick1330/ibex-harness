<script setup lang="ts">
import type { ContentNavigationItem } from '@nuxt/content'

interface SearchLink {
  label: string
  description?: string
  to: string
  icon?: string
}

const props = defineProps<{
  navigation?: ContentNavigationItem[]
}>()

const route = useRoute()
const { forced: forcedColorMode } = useDocusColorMode()

type SearchScope = 'landing' | 'docs' | 'blog' | 'benchmarks' | 'releases'

const scope = computed<SearchScope>(() => {
  if (route.path === '/docs' || route.path.startsWith('/docs/')) return 'docs'
  if (route.path === '/blog' || route.path.startsWith('/blog/')) return 'blog'
  if (route.path === '/benchmarks') return 'benchmarks'
  if (route.path === '/releases') return 'releases'
  return 'landing'
})

const { data: files } = useLazyAsyncData(
  () => `search_sections_${scope.value}`,
  () => {
    if (scope.value === 'docs') return queryCollectionSearchSections('docs')
    if (scope.value === 'blog') return queryCollectionSearchSections('blog')
    return Promise.resolve([])
  },
  { server: false, default: () => [], watch: [scope] },
)

const { data: blogPosts } = useLazyAsyncData(
  'search_blog_navigation',
  async () => {
    const posts = await queryCollection('blog').order('date', 'DESC').all()
    return posts.map(post => ({
      title: String(post.title || post.path),
      path: String(post.path),
    })) as ContentNavigationItem[]
  },
  { server: false, default: () => [] },
)

const landingLinks: SearchLink[] = [
  { label: 'Overview', description: 'Memory for agents. Control for you. The self-hosted boundary between your agent and the model.', to: '/', icon: 'i-lucide-house' },
  { label: 'How it works', description: 'One boundary. Six jobs: identity, tenant-scoped recall, context budget, provider routing, streaming, and evidence.', to: '/#how-it-works', icon: 'i-lucide-workflow' },
  { label: 'Drop-in proxy', description: 'Keep the OpenAI-compatible request. Change where memory and context are assembled.', to: '/#drop-in', icon: 'i-lucide-arrow-right-left' },
  { label: 'Evidence and status', description: 'What works today and what we do not claim. Every capability keeps a status, scope, and date.', to: '/#proof', icon: 'i-lucide-list-checks' },
  { label: 'Run it locally', description: 'Quickstart commands for Docker Compose, migrations, and the local stack.', to: '/#quickstart', icon: 'i-lucide-terminal' },
  { label: 'Benchmarks', description: 'Published proxy, retrieval, write, and extraction measurements with methodology.', to: '/benchmarks', icon: 'i-lucide-chart-no-axes-column' },
  { label: 'Releases', description: 'Human-readable release notes generated from the repository changelog.', to: '/releases', icon: 'i-lucide-tag' },
  { label: 'Engineering notes', description: 'Technical essays on agent memory, request-path security, and context assembly.', to: '/blog', icon: 'i-lucide-notebook-pen' },
  { label: 'Documentation', description: 'Architecture, auth, proxy, memory, context, API reference, and operations.', to: '/docs', icon: 'i-lucide-book-open' },
]

const benchmarkLinks: SearchLink[] = [
  { label: 'Benchmarks overview', description: 'Published measurements, methodology, and evidence boundaries.', to: '/benchmarks', icon: 'i-lucide-chart-no-axes-column' },
  { label: 'Proxy latency', description: 'Proxy overhead percentiles across runs.', to: '/benchmarks#proxy', icon: 'i-lucide-timer' },
  { label: 'Retrieval quality', description: 'pgvector HNSW recall and search latency by corpus size.', to: '/benchmarks#retrieval', icon: 'i-lucide-database' },
  { label: 'Context ranking', description: 'Ranking and packing evidence for the context assembly path.', to: '/benchmarks#ranking', icon: 'i-lucide-list-ordered' },
  { label: 'Memory writes', description: 'Write-path measurements and gate evidence.', to: '/benchmarks#writes', icon: 'i-lucide-pen-line' },
  { label: 'Extraction', description: 'Worker extraction categories and summary measurements.', to: '/benchmarks#extraction', icon: 'i-lucide-scan-text' },
  { label: 'Methodology', description: 'How each benchmark is run, capped, and reported.', to: '/benchmarks#method', icon: 'i-lucide-flask-conical' },
  { label: 'Raw data', description: 'Source tables and receipts behind the published numbers.', to: '/benchmarks#raw-data', icon: 'i-lucide-table' },
]

const releaseLinks: SearchLink[] = [
  { label: 'All releases', description: 'Every release in the changelog, newest first.', to: '/releases', icon: 'i-lucide-tag' },
  { label: 'Latest release', description: 'The newest user-visible changes, security fixes, and migrations.', to: '/releases', icon: 'i-lucide-sparkles' },
  { label: 'CHANGELOG.md', description: 'The raw changelog in the repository.', to: 'https://github.com/Rick1330/ibex-harness/blob/main/CHANGELOG.md', icon: 'i-lucide-file-text' },
  { label: 'GitHub releases', description: 'Published release artifacts on GitHub.', to: 'https://github.com/Rick1330/ibex-harness/releases', icon: 'i-lucide-github' },
]

const links = computed<SearchLink[] | undefined>(() => {
  if (scope.value === 'landing') return landingLinks
  if (scope.value === 'benchmarks') return benchmarkLinks
  if (scope.value === 'releases') return releaseLinks
  return undefined
})

const navigation = computed<ContentNavigationItem[] | undefined>(() => {
  if (scope.value === 'docs') return props.navigation
  if (scope.value === 'blog') return blogPosts.value
  return undefined
})
</script>

<template>
  <LazyUContentSearch
    :files="files"
    :navigation="navigation"
    :links="links"
    :color-mode="!forcedColorMode"
  />
</template>
