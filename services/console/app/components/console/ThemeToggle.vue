<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { Moon, Sun, SunMoon } from "@lucide/vue"

const colorMode = useColorMode()
const mounted = ref(false)

onMounted(() => {
  mounted.value = true
})

const next = computed(() => (colorMode.value === "dark" ? "light" : "dark"))
const label = computed(() => (mounted.value ? `Switch to ${next.value} theme` : "Toggle color theme"))

function toggle() {
  colorMode.preference = next.value
}
</script>

<template>
  <button
    type="button"
    class="ix-theme-button"
    :aria-label="label"
    :title="label"
    @click="toggle"
  >
    <Sun v-if="mounted && colorMode.value === 'dark'" :size="17" :stroke-width="1.75" aria-hidden="true" />
    <Moon v-else-if="mounted" :size="17" :stroke-width="1.75" aria-hidden="true" />
    <SunMoon v-else :size="17" :stroke-width="1.75" aria-hidden="true" />
  </button>
</template>

<style scoped>
.ix-theme-button {
  display: inline-flex;
  width: 2rem;
  height: 2rem;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  color: var(--ix-fg-3);
  transition: color 120ms ease, background-color 120ms ease;
}

.ix-theme-button:hover {
  background: var(--ix-raised);
  color: var(--ix-fg-1);
}
</style>
