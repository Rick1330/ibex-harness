<script setup lang="ts">
import { computed } from "vue"

type Token = { text: string; kind: "text" | "redacted" | "match" }

const props = withDefaults(
  defineProps<{
    text: string
    query?: string
    untrusted?: boolean
  }>(),
  { query: "", untrusted: false },
)

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

const tokens = computed<Token[]>(() => {
  const query = props.query.trim()
  const matcher = query ? new RegExp(`(${escapeRegExp(query)})`, "gi") : null
  const result: Token[] = []

  function pushPlain(value: string): void {
    if (!value) return
    if (!matcher) {
      result.push({ text: value, kind: "text" })
      return
    }
    let cursor = 0
    for (const match of value.matchAll(matcher)) {
      const index = match.index ?? 0
      if (index > cursor) result.push({ text: value.slice(cursor, index), kind: "text" })
      result.push({ text: match[0], kind: "match" })
      cursor = index + match[0].length
    }
    if (cursor < value.length) result.push({ text: value.slice(cursor), kind: "text" })
  }

  for (const part of props.text.split(/(\[REDACTED\])/g)) {
    if (!part) continue
    if (part === "[REDACTED]") result.push({ text: part, kind: "redacted" })
    else pushPlain(part)
  }

  return result
})
</script>

<template>
  <span :class="untrusted && 'italic text-fg-3'">
    <template v-if="untrusted">“</template>
    <template v-for="(token, index) in tokens" :key="index">
      <code
        v-if="token.kind === 'redacted'"
        class="mx-0.5 inline-flex items-center rounded border border-line-subtle bg-surface-2 px-1 py-0.5 font-mono text-[0.625rem] leading-none font-medium text-fg-2"
      >{{ token.text }}</code>
      <mark
        v-else-if="token.kind === 'match'"
        class="rounded-sm bg-memory-tint px-0.5 text-fg-1"
      >{{ token.text }}</mark>
      <template v-else>{{ token.text }}</template>
    </template>
    <template v-if="untrusted">”</template>
  </span>
</template>
