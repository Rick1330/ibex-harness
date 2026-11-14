<script setup lang="ts">
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"

definePageMeta({ layout: false })
useHead({ title: "Signing out · IBEX Console" })

const router = useRouter()
const csrf = useCookie("ibex_csrf")
const message = ref("Signing out…")

onMounted(async () => {
  const headers: Record<string, string> = {}
  if (csrf.value) headers["X-CSRF-Token"] = csrf.value

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
