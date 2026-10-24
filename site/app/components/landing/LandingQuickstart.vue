<script setup lang="ts">
import { tokenizeCodeLine } from '~/utils/code'

const commands = [
  'git clone https://github.com/Rick1330/ibex-harness.git',
  'cd ibex-harness',
  'cp .env.example .env',
  'make compose-dev-up',
  'make db-migrate',
  'make db-seed',
  'make dev-smoke',
].join('\n')

const copied = ref(false)
const lines = computed(() => commands.split('\n').map(line => ({
  tokens: tokenizeCodeLine(line, 'shell'),
})))
let copiedTimer: ReturnType<typeof setTimeout> | undefined

async function copyCommands() {
  try {
    await navigator.clipboard.writeText(commands)
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
  <section id="quickstart" class="quickstart" aria-labelledby="quickstart-title">
    <div class="quickstart-inner site-shell">
      <div class="quickstart-topline">
        <span>04 / Run it</span>
        <span>Local stack · MIT</span>
      </div>

      <div class="quickstart-grid">
        <div class="quickstart-copy">
          <p class="quickstart-kicker">Start with mock mode</p>
          <h2 id="quickstart-title">Run the boundary locally.</h2>
          <p class="quickstart-lede">
            Start Postgres, Redis, and the services with Docker Compose. Mock mode returns a
            response without a provider key, so you can inspect a request before connecting a
            model.
          </p>

          <ol class="quickstart-steps">
            <li>
              <span class="quickstart-step-index">01</span>
              <div>
                <strong>Prepare</strong>
                <p>Clone the repository and copy the example environment.</p>
              </div>
            </li>
            <li>
              <span class="quickstart-step-index">02</span>
              <div>
                <strong>Start the stack</strong>
                <p>Postgres, Redis, and the local services come up together.</p>
              </div>
            </li>
            <li>
              <span class="quickstart-step-index">03</span>
              <div>
                <strong>Verify the seam</strong>
                <p>Migrate, seed, and run the smoke path in mock mode.</p>
              </div>
            </li>
          </ol>

          <div class="quickstart-actions">
            <NuxtLink to="/docs/getting-started/quickstart" class="quickstart-button">
              Full quickstart
              <LandingGlyph name="arrow-right" class="size-3.5" />
            </NuxtLink>
            <a
              href="https://github.com/Rick1330/ibex-harness"
              target="_blank"
              rel="noreferrer"
              class="quickstart-link"
            >
              View source
              <UIcon name="i-simple-icons-github" class="size-3.5" />
            </a>
          </div>

          <p class="quickstart-note">
            The full quickstart covers separate service terminals and real provider keys.
          </p>
        </div>

        <div class="landing-code quickstart-code">
          <div class="landing-code-bar">
            <span class="landing-code-label">
              <LandingGlyph name="terminal" class="size-3" />
              quickstart.sh
            </span>
            <button
              type="button"
              class="landing-code-copy"
              :class="{ 'is-copied': copied }"
              :aria-label="copied ? 'Copied quickstart commands' : 'Copy all quickstart commands'"
              title="Copy quickstart commands"
              @click="copyCommands"
            >
              <LandingGlyph :name="copied ? 'check' : 'copy'" class="size-3.5" />
              {{ copied ? 'Copied' : 'Copy all' }}
            </button>
          </div>

          <pre class="landing-code-body"><code><span
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
            <span>Mock mode returns 200 without a provider key.</span>
            <NuxtLink to="/docs/getting-started/quickstart">
              /docs/getting-started/quickstart
            </NuxtLink>
          </div>

          <span class="landing-code-sr" aria-live="polite">{{ copied ? 'Commands copied' : '' }}</span>
        </div>
      </div>

      <div class="quickstart-foot">
        <span>MIT licensed · self-hosted · no hosted control plane</span>
        <div class="quickstart-foot-links">
          <NuxtLink to="/docs/getting-started/quickstart">Quickstart</NuxtLink>
          <NuxtLink to="/docs/architecture/overview">Architecture</NuxtLink>
          <NuxtLink to="/benchmarks">Benchmarks</NuxtLink>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.quickstart {
  position: relative;
  overflow: hidden;
  border-top: 1px solid #262a2d;
  background: #090a0b;
  color: #f2f2ed;
}

.quickstart::before {
  content: "";
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(to right, rgb(255 255 255 / 0.04) 1px, transparent 1px),
    linear-gradient(to bottom, rgb(255 255 255 / 0.04) 1px, transparent 1px);
  background-size: 84px 84px;
  mask-image: linear-gradient(to bottom, black, transparent 82%);
  pointer-events: none;
}

.quickstart-inner {
  position: relative;
  z-index: 1;
  padding-block: clamp(1.25rem, 2.2vw, 1.75rem) 1.5rem;
}

.quickstart-topline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding-bottom: 0.9rem;
  border-bottom: 1px solid rgb(255 255 255 / 0.1);
  font-family: var(--font-mono);
  font-size: 0.57rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #8d938d;
}

.quickstart-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
  gap: clamp(2.5rem, 5vw, 5.5rem);
  align-items: center;
  padding: clamp(3rem, 5.5vw, 5.5rem) 0;
}

.quickstart-copy {
  min-width: 0;
}

.quickstart-kicker {
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  margin: 0;
  font-family: var(--font-mono);
  font-size: 0.62rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #d8ff4f;
}

.quickstart-kicker::before {
  content: "";
  width: 1.45rem;
  height: 1px;
  background: #d8ff4f;
}

.quickstart-copy h2 {
  max-width: 10ch;
  margin: 1rem 0 0;
  font-family: var(--font-sans);
  font-size: clamp(2.9rem, 4.8vw, 4.8rem);
  font-weight: 560;
  line-height: 0.92;
  letter-spacing: -0.065em;
}

.quickstart-lede {
  max-width: 31rem;
  margin: 1.25rem 0 0;
  font-size: 0.98rem;
  line-height: 1.7;
  color: #9a9d98;
  text-wrap: pretty;
}

.quickstart-steps {
  display: grid;
  gap: 0;
  margin: 1.5rem 0 0;
  padding: 0;
  list-style: none;
}

.quickstart-steps li {
  display: grid;
  grid-template-columns: 2rem minmax(0, 1fr);
  gap: 0.75rem;
  padding: 0.8rem 0;
  border-top: 1px solid rgb(255 255 255 / 0.1);
}

.quickstart-step-index {
  padding-top: 0.08rem;
  font-family: var(--font-mono);
  font-size: 0.56rem;
  color: #d8ff4f;
}

.quickstart-steps strong {
  display: block;
  font-size: 0.9rem;
  font-weight: 560;
  line-height: 1.3;
  letter-spacing: -0.02em;
  color: #f2f2ed;
}

.quickstart-steps p {
  margin: 0.24rem 0 0;
  font-size: 0.82rem;
  line-height: 1.55;
  color: #9a9d98;
  text-wrap: pretty;
}

.quickstart-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 1rem;
  margin-top: 1.6rem;
}

.quickstart-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  min-height: 2.7rem;
  padding: 0.65rem 1rem;
  border: 1px solid #d8ff4f;
  background: #d8ff4f;
  font-family: var(--font-mono);
  font-size: 0.61rem;
  font-weight: 600;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: #0a0b0c;
  transition: background-color 140ms ease, border-color 140ms ease, color 140ms ease, transform 140ms ease;
}

.quickstart-button:hover {
  transform: translateY(-1px);
  border-color: #f2f2ed;
  background: #f2f2ed;
}

@media (prefers-reduced-motion: reduce) {
  .quickstart-button,
  .quickstart-button:hover {
    transform: none;
    transition: none;
  }
}

.quickstart-link {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-family: var(--font-mono);
  font-size: 0.6rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #f2f2ed;
  transition: color 140ms ease;
}

.quickstart-link:hover {
  color: #d8ff4f;
}

.quickstart-note {
  margin: 1.1rem 0 0;
  font-size: 0.76rem;
  line-height: 1.6;
  color: #7f8984;
}

.quickstart-code {
  border-color: rgb(255 255 255 / 0.14);
  box-shadow: 0 32px 80px -58px #000;
}

.quickstart-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem 1.5rem;
  padding-top: 1.1rem;
  border-top: 1px solid rgb(255 255 255 / 0.1);
  font-family: var(--font-mono);
  font-size: 0.54rem;
  letter-spacing: 0.06em;
  color: #7f8984;
}

.quickstart-foot-links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.8rem 1.1rem;
}

.quickstart-foot-links a {
  color: #b9beb8;
  transition: color 140ms ease;
}

.quickstart-foot-links a:hover {
  color: #d8ff4f;
}

@media (max-width: 1024px) {
  .quickstart-grid {
    grid-template-columns: 1fr;
    align-items: start;
  }

  .quickstart-copy {
    max-width: 36rem;
  }

  .quickstart-copy h2 {
    max-width: 13ch;
  }

  .quickstart-code {
    max-width: 48rem;
  }
}

@media (max-width: 680px) {
  .quickstart-grid {
    padding: 2.75rem 0;
  }

  .quickstart-copy h2 {
    font-size: clamp(2.5rem, 11vw, 3.4rem);
  }

  .quickstart-foot > span {
    display: none;
  }
}
</style>
