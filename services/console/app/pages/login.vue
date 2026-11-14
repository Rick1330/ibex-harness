<script setup lang="ts">
import { ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { safeLoginNext } from "@/lib/navigation"

definePageMeta({ layout: false })
useHead({ title: "Sign in · IBEX Console" })

const route = useRoute()
const router = useRouter()

const pat = ref("")
const submitting = ref(false)
const errorMessage = ref<string | null>(null)

const nextTarget = safeLoginNext(route.query.next)

function messageFrom(error: unknown): string {
  const data = (error as { data?: { error?: { message?: string } } } | null)?.data
  const message = data?.error?.message
  if (typeof message === "string" && message.length > 0) return message
  return "Sign-in failed. Try again."
}

async function submit(): Promise<void> {
  if (submitting.value) return
  const token = pat.value.trim()
  if (!token) {
    errorMessage.value = "Enter a personal access token."
    return
  }

  submitting.value = true
  errorMessage.value = null
  try {
    // The PAT travels once, in the body, to the same-origin BFF route. It is
    // never placed in a URL, storage, or a log, and is cleared from the field.
    await $fetch("/api/operator/session/login", {
      method: "POST",
      body: { pat: token },
    })
    pat.value = ""
    await router.replace(nextTarget)
  } catch (error) {
    // The BFF returns a stable message for 401/403; never echo the token.
    errorMessage.value = messageFrom(error)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="flex min-h-svh items-center justify-center bg-canvas px-4 py-10">
    <section class="w-full max-w-sm rounded-xl border border-line bg-surface p-6">
      <div class="mb-6 flex items-center gap-2.5">
        <span class="flex size-8 items-center justify-center rounded-md border border-line bg-raised">
          <img src="/brand/ibex-mark-light.png" alt="" class="size-5 dark:hidden" >
          <img src="/brand/ibex-mark-dark.png" alt="" class="hidden size-5 dark:block" >
        </span>
        <div>
          <h1 class="text-base leading-6 font-semibold tracking-tight text-fg-1">Sign in to IBEX Console</h1>
          <p class="text-[0.6875rem] leading-4 text-fg-3">Operator workspace</p>
        </div>
      </div>

      <form class="space-y-4" novalidate @submit.prevent="submit">
        <div class="space-y-1.5">
          <label for="operator-pat" class="block text-xs font-medium text-fg-2">Personal access token</label>
          <input
            id="operator-pat"
            v-model="pat"
            type="password"
            name="pat"
            autocomplete="off"
            autocapitalize="none"
            spellcheck="false"
            class="w-full rounded-md border border-line bg-canvas px-3 py-2 font-mono text-sm text-fg-1 outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
            :disabled="submitting"
            :aria-invalid="Boolean(errorMessage)"
            aria-describedby="operator-pat-help"
          >
          <p id="operator-pat-help" class="text-[0.6875rem] leading-4 text-fg-3">
            The token is exchanged once for an HttpOnly session cookie. It is never stored in this browser.
          </p>
        </div>

        <p
          v-if="errorMessage"
          role="alert"
          aria-live="polite"
          class="rounded-md border border-crit/40 bg-crit/10 px-3 py-2 text-xs text-crit"
        >
          {{ errorMessage }}
        </p>

        <button
          type="submit"
          class="w-full rounded-md bg-accent px-3 py-2 text-sm font-semibold text-accent-foreground transition-opacity disabled:opacity-60"
          :disabled="submitting"
        >
          {{ submitting ? "Signing in…" : "Sign in" }}
        </button>
      </form>
    </section>
  </main>
</template>
