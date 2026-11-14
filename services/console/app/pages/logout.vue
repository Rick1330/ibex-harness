<script setup lang="ts">
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"

definePageMeta({ layout: false })
useHead({ title: "Signing out · IBEX Console" })

type SessionBootstrap = {
  csrf_cookie_name?: string
  csrf_token?: string | null
}

const router = useRouter()
const message = ref("Signing out…")

onMounted(async () => {
  const headers: Record<string, string> = {}
  try {
    // The CSRF cookie name is deployment-configurable, so the BFF resolves the
    // double-submit token from this browser's own cookie. The page never
    // assumes a cookie name.
    const bootstrap = await $fetch<SessionBootstrap>("/api/operator/session/bootstrap")
    if (bootstrap?.csrf_token) headers["X-CSRF-Token"] = bootstrap.csrf_token
  } catch {
    // Without the token the API rejects the revocation before its handler runs.
    // The BFF's unconditional deletions still clear this browser's cookies, so
    // an unreachable bootstrap must not strand the operator on a protected page.
  }

  try {
    // The API revokes the session family and clears the cookies. The BFF relays
    // the deletions before reporting status, so an invalid session still signs
    // the browser out.
    await $fetch("/api/operator/session/logout", { method: "POST", headers })
  } catch {
    // Revocation can fail when the API is unreachable, but the browser must not
    // stay on a protected page; the login page can replace any stale session.
  }
  await router.replace("/login")
})
</script>

<template>
  <main class="flex min-h-svh items-center justify-center bg-canvas px-4 py-10">
    <section class="w-full max-w-sm rounded-xl border border-line bg-surface p-6 text-center">
      <output class="block text-sm text-fg-2">{{ message }}</output>
      <NuxtLink
        to="/login"
        class="mt-4 inline-block text-xs text-accent underline-offset-4 hover:underline"
      >
        Return to sign in
      </NuxtLink>
    </section>
  </main>
</template>
