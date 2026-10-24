<script setup lang="ts">
import { tokenizeCodeLine, type CodeLanguage } from '~/utils/code'

interface Snippet {
  label: string
  language: CodeLanguage
  code: string
}

const snippets: Snippet[] = [
  {
    label: 'curl',
    language: 'shell',
    code: [
      'curl -s -w "\\nHTTP %{http_code}\\n" \\',
      '  -X POST "http://localhost:8080/v1/chat/completions" \\',
      '  -H "Authorization: Bearer $IBEX_TEST_PAT" \\',
      '  -H "X-IBEX-Agent-ID: $IBEX_TEST_AGENT_ID" \\',
      '  -H "Content-Type: application/json" \\',
      '  -d \'{"model":"gpt-4o","messages":[{"role":"user","content":"hello"}]}\'',
    ].join('\n'),
  },
  {
    label: 'TypeScript',
    language: 'ts',
    code: [
      'const res = await fetch("http://localhost:8080/v1/chat/completions", {',
      '  method: "POST",',
      '  headers: {',
      '    Authorization: `Bearer ${process.env.IBEX_TEST_PAT}`,',
      '    "X-IBEX-Agent-ID": process.env.IBEX_TEST_AGENT_ID!,',
      '    "Content-Type": "application/json",',
      '  },',
      '  body: JSON.stringify({',
      '    model: "gpt-4o",',
      '    messages: [{ role: "user", content: "hello" }],',
      '  }),',
      '});',
      '',
      'console.log(res.status, await res.text());',
    ].join('\n'),
  },
  {
    label: 'Python',
    language: 'python',
    code: [
      'import os',
      'import requests',
      '',
      'headers = {',
      '    "Authorization": f"Bearer {os.environ[\'IBEX_TEST_PAT\']}",',
      '    "X-IBEX-Agent-ID": os.environ["IBEX_TEST_AGENT_ID"],',
      '    "Content-Type": "application/json",',
      '}',
      '',
      'res = requests.post(',
      '    "http://localhost:8080/v1/chat/completions",',
      '    headers=headers,',
      '    json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hello"}]},',
      '    timeout=10,',
      ')',
      '',
      'print(res.status_code, res.text)',
    ].join('\n'),
  },
]

const active = ref(0)
const copied = ref(false)
const tabRefs = ref<HTMLButtonElement[]>([])
let copiedTimer: ReturnType<typeof setTimeout> | undefined

const current = computed(() => snippets[active.value] ?? snippets[0]!)
const lines = computed(() => current.value.code.split('\n').map((line) => {
  return {
    tokens: tokenizeCodeLine(line, current.value.language),
  }
}))

function select(index: number) {
  active.value = index
  copied.value = false
  nextTick(() => tabRefs.value[index]?.focus())
}

function move(event: KeyboardEvent, index: number) {
  const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End']
  if (!keys.includes(event.key)) return

  event.preventDefault()
  const next = event.key === 'ArrowLeft'
    ? (index - 1 + snippets.length) % snippets.length
    : event.key === 'ArrowRight'
      ? (index + 1) % snippets.length
      : event.key === 'Home'
        ? 0
        : snippets.length - 1

  select(next)
}

async function copyCode() {
  try {
    await navigator.clipboard.writeText(current.value.code)
  } catch {
    return
  }

  copied.value = true
  clearTimeout(copiedTimer)
  copiedTimer = setTimeout(() => {
    copied.value = false
  }, 1600)
}

onBeforeUnmount(() => clearTimeout(copiedTimer))
</script>

<template>
  <div class="landing-code">
    <div class="landing-code-bar">
      <div class="landing-code-tablist" role="tablist" aria-label="Chat completion examples">
        <button
          v-for="(snippet, index) in snippets"
          :id="`landing-code-tab-${index}`"
          :key="snippet.label"
          :ref="el => { if (el) tabRefs[index] = el as HTMLButtonElement }"
          type="button"
          role="tab"
          class="landing-code-tab"
          :class="{ 'is-active': active === index }"
          :aria-selected="active === index"
          aria-controls="landing-code-panel"
          :tabindex="active === index ? 0 : -1"
          @click="select(index)"
          @keydown="move($event, index)"
        >
          {{ snippet.label }}
        </button>
      </div>

      <button
        type="button"
        class="landing-code-copy"
        :class="{ 'is-copied': copied }"
        :aria-label="`Copy ${current.label} example`"
        :title="`Copy ${current.label} example`"
        @click="copyCode"
      >
        <LandingGlyph :name="copied ? 'check' : 'copy'" class="size-3.5" />
        {{ copied ? 'Copied' : 'Copy' }}
      </button>
    </div>

    <pre
      id="landing-code-panel"
      class="landing-code-body"
      tabindex="0"
      role="tabpanel"
      :aria-labelledby="`landing-code-tab-${active}`"
    ><code><span
        v-for="(line, index) in lines"
        :key="index"
        class="landing-code-line"
      ><span class="landing-code-ln" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</span><span class="landing-code-text"><span
          v-for="(token, tokenIndex) in line.tokens"
          :key="tokenIndex"
          class="landing-code-token"
          :class="`landing-code-token--${token.kind}`"
        >{{ token.text }}</span></span></span></code></pre>

    <div class="landing-code-foot">
      <span>Tenant comes from the token. Never from the body.</span>
      <NuxtLink to="/docs/api-reference/chat-completions">
        API reference
        <LandingGlyph name="arrow-up-right" class="size-3" />
      </NuxtLink>
    </div>

    <span class="landing-code-sr" aria-live="polite">{{ copied ? 'Example copied' : '' }}</span>
  </div>
</template>
