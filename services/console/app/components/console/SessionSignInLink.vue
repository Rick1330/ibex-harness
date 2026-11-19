<script setup lang="ts">
/**
 * The remedy every session refusal names: a real link to the sign-in page that
 * returns to the surface that refused. Shared by the verdict and empty-state
 * primitives so one refusal cannot offer a different affordance from another.
 */
import { computed } from "vue"
import { loginHref } from "@/lib/navigation"

const route = useRoute()
const href = computed(() => loginHref(route.fullPath))
</script>

<template>
  <NuxtLink :to="href" class="ix-button-secondary">Sign in</NuxtLink>
</template>
