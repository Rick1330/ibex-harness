export default defineAppConfig({
  docus: {
    locale: 'en',
  },
  search: {
    fts: false,
  },
  seo: {
    title: 'IBEX Harness',
    titleTemplate: '%s · IBEX Harness',
    description: 'The self-hosted memory and context layer for AI agents. OpenAI-compatible, tenant-isolated, and inspectable.',
  },
  header: {
    title: 'IBEX Harness',
    logo: {
      light: '/brand/ibex-mark-light.png',
      dark: '/brand/ibex-mark-dark.png',
      alt: 'IBEX Harness',
      favicon: '/brand/android-chrome-192x192.png',
      display: 'logo',
    },
  },
  socials: {
    github: 'https://github.com/Rick1330/ibex-harness',
    x: 'https://x.com/ibexharness',
  },
  github: {
    url: 'https://github.com/Rick1330/ibex-harness',
    branch: 'main',
    rootDir: 'site',
  },
  ui: {
    colors: {
      primary: 'lime',
      neutral: 'zinc',
    },
    pageHero: {
      slots: {
        title: 'font-semibold tracking-[-0.045em] sm:text-6xl',
        container: '!pb-0',
      },
    },
  },
  toc: {
    title: 'On this page',
    bottom: {
      title: 'Evidence',
      links: [
        {
          icon: 'i-lucide-list-checks',
          label: 'Status ledger',
          to: '/docs/architecture/status-and-evidence',
        },
      ],
    },
  },
})
