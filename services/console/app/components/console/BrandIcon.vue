<script setup lang="ts">
import { computed } from "vue"
import openai from "@/assets/brands/openai.svg"
import anthropic from "@/assets/brands/anthropic.svg"
import google from "@/assets/brands/google.svg"
import gemini from "@/assets/brands/gemini-color.svg"
import azure from "@/assets/brands/azure-color.svg"
import mistral from "@/assets/brands/mistral-color.svg"
import meta from "@/assets/brands/meta-color.svg"
import vllm from "@/assets/brands/vllm-color.svg"
import deepseek from "@/assets/brands/deepseek-color.svg"
import ollama from "@/assets/brands/ollama.svg"
import claude from "@/assets/brands/claude-color.svg"
import xai from "@/assets/brands/xai.svg"
import qwen from "@/assets/brands/qwen-color.svg"
import cohere from "@/assets/brands/cohere-color.svg"

const props = withDefaults(
  defineProps<{
    id: string
    size?: number
    label?: string | null
    muted?: boolean
  }>(),
  { size: 16, label: null, muted: false },
)

const ICONS: Record<string, string> = {
  openai,
  anthropic,
  claude,
  google,
  gemini,
  azure,
  "azure-openai": azure,
  mistral,
  meta,
  llama: meta,
  vllm,
  "local-vllm": vllm,
  ollama,
  deepseek,
  xai,
  grok: xai,
  qwen,
  cohere,
  "gpt-4.1": openai,
  "gpt-4.1-mini": openai,
  "claude-sonnet-4": claude,
  "claude-haiku-3.5": claude,
  "gemini-2.5-pro": gemini,
  "llama-3.3-70b": meta,
  "mistral-large-2": mistral,
  "text-embedding-3-small": openai,
}

const key = computed(() => props.id.toLowerCase())
const source = computed(() => ICONS[key.value] ?? null)
const mono = computed(() => ["openai", "anthropic", "google", "ollama", "xai", "grok", "gpt-4.1", "gpt-4.1-mini"].includes(key.value))
const alt = computed(() => props.label ?? `${props.id} logo`)
</script>

<template>
  <img
    v-if="source"
    :src="source"
    :alt="alt"
    :width="size"
    :height="size"
    :class="['shrink-0 object-contain', muted ? 'opacity-70 grayscale' : '', mono ? 'dark:invert' : '']"
    decoding="async"
    draggable="false"
  >
</template>
