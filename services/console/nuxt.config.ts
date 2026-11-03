import tailwindcss from "@tailwindcss/vite"

export default defineNuxtConfig({
  compatibilityDate: "2026-10-20",
  devtools: { enabled: false },
  ssr: true,
  modules: ["shadcn-nuxt", "@nuxt/eslint", "@nuxtjs/color-mode"],
  vite: {
    plugins: [tailwindcss()],
  },
  css: ["~/assets/css/main.css"],
  components: [{ path: "~/components", pathPrefix: false }],
  colorMode: {
    classSuffix: "",
    preference: "system",
    fallback: "dark",
    storageKey: "ibex-console-theme",
  },
  shadcn: {
    prefix: "",
    componentDir: "~/components/ui",
  },
  runtimeConfig: {
    operatorApiOrigin: "",
    operatorSessionCookieName: "ibex_session",
    consoleReadOnly: "1",
    public: {
      ibexEnv: "local",
    },
  },
  nitro: {
    preset: "node-server",
  },
  app: {
    head: {
      htmlAttrs: { lang: "en" },
      title: "IBEX Console",
      meta: [
        {
          name: "description",
          content:
            "IBEX operator console for evidence-backed sessions, traces, memories, directives, and platform health.",
        },
        { name: "theme-color", content: "#f1f1ec", media: "(prefers-color-scheme: light)" },
        { name: "theme-color", content: "#090a0b", media: "(prefers-color-scheme: dark)" },
        { name: "color-scheme", content: "light dark" },
      ],
    },
  },
  typescript: {
    strict: true,
  },
  eslint: {
    config: {
      stylistic: false,
    },
  },
})
