<script setup lang="ts">
const props = defineProps<{
  name: string
  role: string
  githubUrl: string
  xUrl: string
  shareUrl: string
}>()

const copied = ref(false)
let copiedTimer: ReturnType<typeof setTimeout> | undefined

const avatar = 'https://github.com/Rick1330.png?size=160'

async function copyLink() {
  let ok = false
  try {
    await navigator.clipboard.writeText(props.shareUrl)
    ok = true
  } catch {
    const input = document.createElement('textarea')
    input.value = props.shareUrl
    input.setAttribute('readonly', '')
    input.style.position = 'fixed'
    input.style.opacity = '0'
    document.body.appendChild(input)
    input.select()
    try {
      ok = document.execCommand('copy')
    } finally {
      input.remove()
    }
  }
  if (!ok) return
  copied.value = true
  clearTimeout(copiedTimer)
  copiedTimer = setTimeout(() => {
    copied.value = false
  }, 2000)
}

onBeforeUnmount(() => clearTimeout(copiedTimer))
</script>

<template>
  <aside class="border-t border-[var(--site-line)] pt-5 lg:border-t-0 lg:pt-1">
    <div class="flex items-center gap-3.5">
      <img
        :src="avatar"
        :alt="props.name"
        width="56"
        height="56"
        class="size-14 shrink-0 rounded-full border border-[var(--site-line-strong)] object-cover"
        loading="lazy"
      >
      <div class="min-w-0">
        <p class="m-0 text-sm font-medium tracking-[-0.01em]">{{ props.name }}</p>
        <p class="m-0 mt-1 text-xs leading-relaxed text-[var(--site-muted)]">{{ props.role }}</p>
      </div>
    </div>

    <div class="mt-4 flex items-center gap-2">
      <a
        :href="props.githubUrl"
        target="_blank"
        rel="noreferrer"
        class="grid size-9 place-items-center rounded-full border border-[var(--site-line)] text-[var(--site-muted)] transition-colors hover:border-[var(--site-line-strong)] hover:text-[var(--site-ink)]"
        aria-label="GitHub profile"
        title="GitHub"
      >
        <UIcon name="i-simple-icons-github" class="size-4" />
      </a>
      <a
        :href="props.xUrl"
        target="_blank"
        rel="noreferrer"
        class="grid size-9 place-items-center rounded-full border border-[var(--site-line)] text-[var(--site-muted)] transition-colors hover:border-[var(--site-line-strong)] hover:text-[var(--site-ink)]"
        aria-label="X profile"
        title="X"
      >
        <UIcon name="i-simple-icons-x" class="size-3.5" />
      </a>
      <button
        type="button"
        class="grid size-9 place-items-center rounded-full border border-[var(--site-line)] text-[var(--site-muted)] transition-colors hover:border-[var(--site-line-strong)] hover:text-[var(--site-ink)]"
        :aria-label="copied ? 'Direct link copied' : 'Copy direct link'"
        title="Copy direct link"
        @click="copyLink"
      >
        <UIcon :name="copied ? 'i-lucide-check' : 'i-lucide-link'" class="size-4" />
      </button>
      <span class="sr-only" aria-live="polite">{{ copied ? 'Direct link copied' : '' }}</span>
    </div>
  </aside>
</template>
