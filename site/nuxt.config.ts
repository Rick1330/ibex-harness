export default defineNuxtConfig({
  extends: ['docus'],
  modules: ['@nuxt/eslint'],
  compatibilityDate: '2026-10-20',
  devtools: { enabled: false },
  site: {
    name: 'IBEX Harness',
    url: 'https://ibexharness.com',
    description: 'Memory and context infrastructure for agents that have to work in the real world.',
  },
  content: {
    experimental: { sqliteConnector: 'native' },
    build: {
      markdown: {
        highlight: {
          theme: { default: 'vitesse-light', dark: 'vitesse-dark' },
          langs: ['bash', 'diff', 'json', 'js', 'ts', 'html', 'css', 'vue', 'shell', 'mdc', 'md', 'yaml', 'go', 'python', 'sql', 'toml'],
        },
      },
    },
  },
  mdc: {
    highlight: { shikiEngine: 'javascript' },
  },
  llms: {
    domain: 'https://ibexharness.com',
    title: 'IBEX Harness',
    description: 'Agent memory and context infrastructure with explicit evidence and honest status.',
    full: {
      title: 'IBEX Harness documentation',
      description: 'The complete public documentation for IBEX Harness.',
    },
  },
  ogImage: { zeroRuntime: true },
  robots: {
    sitemap: '/sitemap.xml',
  },
  nitro: {
    externals: {
      inline: ['@iconify/utils'],
    },
    prerender: { routes: ['/sitemap.xml', '/robots.txt'] },
  },
  sitemap: {
    excludeAppSources: true,
    sources: ['/api/__sitemap__/blog'],
    urls: ['/', '/benchmarks', '/releases', '/blog'],
  },
  app: {
    head: {
      htmlAttrs: { lang: 'en' },
      link: [
        { rel: 'icon', type: 'image/png', href: '/brand/android-chrome-192x192.png' },
        { rel: 'apple-touch-icon', href: '/brand/android-chrome-192x192.png' },
        { rel: 'manifest', href: '/site.webmanifest' },
      ],
    },
  },
})
