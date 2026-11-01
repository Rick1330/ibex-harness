import withNuxt from "./.nuxt/eslint.config.mjs"

export default withNuxt({
  ignores: [
    ".output/**",
    ".nuxt/**",
    ".nuxt-stale-*/**",
    "test-results/**",
    "playwright-report/**",
  ],
})
