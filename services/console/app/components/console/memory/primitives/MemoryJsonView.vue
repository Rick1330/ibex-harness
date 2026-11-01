<script setup lang="ts">
import { computed } from "vue"

const props = defineProps<{ value: unknown }>()

/** Tokenized JSON for a lightweight highlighter: key, string, number, boolean/null, punctuation. */
const tokens = computed(() => {
  const text = JSON.stringify(props.value, null, 2) ?? "null"
  const pattern = /("(?:\\.|[^"\\])*")(\s*:)?|(\b-?\d+(?:\.\d+)?(?:e[+-]?\d+)?\b)|(\btrue\b|\bfalse\b|\bnull\b)/g
  type Token = { text: string; cls: string | null }
  const list: Token[] = []
  let cursor = 0
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0
    if (index > cursor) list.push({ text: text.slice(cursor, index), cls: null })
    const [, string, colon, number, literal] = match
    if (string && colon) {
      list.push({ text: string, cls: "text-viz-3" })
      list.push({ text: colon, cls: "text-fg-3" })
    } else if (string) list.push({ text: string, cls: "text-ok" })
    else if (number) list.push({ text: number, cls: "text-memory" })
    else if (literal) list.push({ text: literal, cls: "text-viz-2" })
    cursor = index + match[0].length
  }
  if (cursor < text.length) list.push({ text: text.slice(cursor), cls: null })
  return list
})
</script>

<template>
  <pre class="ix-scroll max-h-72 overflow-auto rounded-lg border border-line-subtle bg-raised p-3 font-mono text-xs leading-5 whitespace-pre text-fg-2"><code><span
    v-for="(token, index) in tokens"
    :key="index"
    :class="token.cls"
  >{{ token.text }}</span></code></pre>
</template>
