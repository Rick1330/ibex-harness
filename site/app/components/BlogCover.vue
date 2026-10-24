<script setup lang="ts">
interface CoverPost {
  path?: string
  title?: string
  date?: string
  tags?: string[]
  coverIndex?: number
  coverTone?: number
  coverLabel?: string
}

const props = withDefaults(defineProps<{
  post?: CoverPost
  index?: number
  featured?: boolean
}>(), {
  post: () => ({}),
  index: 1,
  featured: false,
})

const displayIndex = computed(() => props.post.coverIndex ?? props.index)
const paddedIndex = computed(() => String(displayIndex.value).padStart(2, '0'))
const tone = computed(() => props.post.coverTone ?? ((displayIndex.value % 3) + 1))
const dateLabel = computed(() => {
  if (!props.post.date) return 'ENGINEERING'
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  }).format(new Date(props.post.date))
})
const primaryTag = computed(() => props.post.coverLabel || props.post.tags?.[0] || 'Engineering')
const tagLabel = computed(() => {
  const count = props.post.tags?.length ?? 0
  if (!count) return 'Engineering note'
  return `${count} ${count === 1 ? 'tag' : 'tags'}`
})
</script>

<template>
  <div
    class="blog-cover"
    :class="[`tone-${tone}`, { 'blog-cover-featured': featured }]"
    aria-hidden="true"
  >
    <div class="blog-cover-grid" />

    <div class="blog-cover-top">
      <span>IBEX / ENGINEERING NOTE</span>
      <span>{{ dateLabel }}</span>
    </div>

    <div class="blog-cover-center">
      <span class="blog-cover-index">{{ paddedIndex }}</span>
      <span class="blog-cover-rule" />
    </div>

    <svg class="blog-cover-rings" viewBox="0 0 300 200" fill="none">
      <circle cx="252" cy="88" r="34" />
      <circle cx="252" cy="88" r="62" />
      <circle cx="252" cy="88" r="90" />
      <circle cx="252" cy="88" r="118" />
      <path d="M196 188 300 84" />
    </svg>

    <div class="blog-cover-bottom">
      <span>{{ primaryTag }}</span>
      <span>{{ tagLabel }}</span>
    </div>
  </div>
</template>

<style scoped>
.blog-cover {
  --cover-accent: #5f8f00;
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  padding: 1rem;
  border: 1px solid var(--site-line);
  background: var(--site-surface-strong);
  color: var(--site-ink);
}

.blog-cover.tone-2 { --cover-accent: #2563eb; }
.blog-cover.tone-3 { --cover-accent: #9b6500; }

:global(.dark) .blog-cover { --cover-accent: #d8ff4f; }
:global(.dark) .blog-cover.tone-2 { --cover-accent: #8fb8ff; }
:global(.dark) .blog-cover.tone-3 { --cover-accent: #f0b45c; }

.blog-cover::after {
  content: "";
  position: absolute;
  inset: 0;
  background:
    radial-gradient(60% 80% at 86% 14%, color-mix(in srgb, var(--cover-accent) 14%, transparent), transparent 68%),
    linear-gradient(145deg, transparent 52%, color-mix(in srgb, var(--site-ink) 4%, transparent) 52.2%, transparent 52.7%);
  pointer-events: none;
}

.blog-cover-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(to right, var(--site-grid) 1px, transparent 1px),
    linear-gradient(to bottom, var(--site-grid) 1px, transparent 1px);
  background-size: 40px 40px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.9), transparent 92%);
  pointer-events: none;
}

.blog-cover-top,
.blog-cover-bottom,
.blog-cover-center {
  position: relative;
  z-index: 1;
}

.blog-cover-top,
.blog-cover-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  font-family: var(--font-mono);
  font-size: 0.52rem;
  letter-spacing: 0.13em;
  text-transform: uppercase;
  color: color-mix(in srgb, var(--site-ink) 52%, transparent);
}

.blog-cover-center {
  display: flex;
  align-items: flex-end;
  gap: 1rem;
}

.blog-cover-index {
  font-size: clamp(4rem, 8vw, 6.5rem);
  font-weight: 560;
  line-height: 0.78;
  letter-spacing: -0.08em;
  color: transparent;
  -webkit-text-stroke: 1px color-mix(in srgb, var(--site-ink) 34%, transparent);
  transition: -webkit-text-stroke-color 220ms ease, transform 500ms cubic-bezier(0.22, 1, 0.36, 1);
}

.blog-cover-rule {
  width: clamp(2.5rem, 6vw, 5rem);
  height: 0.3rem;
  margin-bottom: 0.5rem;
  background: var(--cover-accent);
  transition: width 500ms cubic-bezier(0.22, 1, 0.36, 1);
}

.blog-cover-rings {
  position: absolute;
  right: -2.5rem;
  bottom: -2rem;
  width: 64%;
  max-width: 22rem;
  opacity: 0.7;
  transition: transform 700ms cubic-bezier(0.22, 1, 0.36, 1);
}

.blog-cover-rings circle,
.blog-cover-rings path {
  stroke: var(--cover-accent);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.blog-cover-rings circle {
  opacity: 0.3;
}

.blog-cover-rings path {
  opacity: 0.5;
}

.blog-cover-featured {
  aspect-ratio: 4 / 3;
}

@media (min-width: 1024px) {
  .blog-cover-featured {
    aspect-ratio: auto;
    min-height: 24rem;
    height: 100%;
    padding: 1.35rem;
  }

  .blog-cover-featured .blog-cover-index {
    font-size: clamp(6rem, 10vw, 9rem);
  }
}

@media (max-width: 480px) {
  .blog-cover {
    padding: 0.85rem;
  }

  .blog-cover-rings {
    width: 78%;
  }
}
</style>
