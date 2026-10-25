<script setup lang="ts">
import { nextTabIndex } from '~/utils/tabNavigation'

const tabs = [
  { id: 'request', label: 'Request', icon: 'request' },
  { id: 'context', label: 'Context', icon: 'database' },
  { id: 'trace', label: 'Trace', icon: 'trace' },
] as const

type TabId = typeof tabs[number]['id']

const active = ref<TabId>('request')
const tabRefs = ref<HTMLButtonElement[]>([])
const copied = ref(false)
let copiedTimer: ReturnType<typeof setTimeout> | undefined

const requestExample = [
  'Authorization: Bearer $IBEX_TOKEN',
  'X-IBEX-Agent-ID: agent_support',
  'Content-Type: application/json',
  '',
  '{',
  '  "model": "gpt-4o",',
  '  "messages": [',
  '    {',
  '      "role": "user",',
  '      "content": "hello"',
  '    }',
  '  ]',
  '}',
].join('\n')

const budgetSegments = [
  { label: 'Directive', width: '18%', value: '18%' },
  { label: 'Memory', width: '34%', value: '34%' },
  { label: 'Messages', width: '38%', value: '38%' },
  { label: 'Reserve', width: '10%', value: '10%' },
]

const boundaryChecks = [
  { icon: 'key', name: 'Token', detail: 'org + agent' },
  { icon: 'shield', name: 'Scope', detail: 'permission bitmap' },
  { icon: 'gauge', name: 'Limit', detail: 'sliding window' },
  { icon: 'database', name: 'Context', detail: 'bounded' },
] as const

const contextRows = [
  { id: 'mem_7f3a', detail: 'tenant-scoped', state: 'kept' },
  { id: 'mem_91c2', detail: 'ranked below directive', state: 'kept' },
  { id: 'mem_b204', detail: 'conflict candidate', state: 'held' },
]

const traceRows = [
  { step: 'auth.verify', detail: 'token to org and agent', state: 'ok', icon: 'key' },
  { step: 'memory.recall', detail: 'tenant filter applied', state: 'ok', icon: 'database' },
  { step: 'context.fit', detail: 'hard cap before forward', state: 'ok', icon: 'gauge' },
  { step: 'provider.stream', detail: 'SSE forwarded', state: 'live', icon: 'radio' },
  { step: 'trace.write', detail: 'after response', state: 'async', icon: 'file-clock' },
] as const

function select(id: TabId) {
  active.value = id
  nextTick(() => tabRefs.value[tabs.findIndex(tab => tab.id === id)]?.focus())
}

function move(event: KeyboardEvent, index: number) {
  const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End']
  if (!keys.includes(event.key)) return

  event.preventDefault()
  select(tabs[nextTabIndex(event.key, index, tabs.length)]!.id)
}

async function copyRequest() {
  copied.value = true
  clearTimeout(copiedTimer)
  copiedTimer = setTimeout(() => {
    copied.value = false
  }, 1600)

  try {
    await navigator.clipboard.writeText(requestExample)
  } catch {
    copied.value = false
    clearTimeout(copiedTimer)
  }
}

onBeforeUnmount(() => clearTimeout(copiedTimer))
</script>

<template>
  <div class="harness-console">
    <div class="console-bar">
      <div class="console-brand">
        <span class="console-mark" aria-hidden="true" />
        <span>IBEX / harness</span>
      </div>
      <span class="console-state">
        <span class="console-state-dot" aria-hidden="true" />
        G0 · Provisional
      </span>
    </div>

    <div class="console-tabs" role="tablist" aria-label="Request inspection">
      <button
        v-for="(tab, index) in tabs"
        :id="`console-tab-${tab.id}`"
        :key="tab.id"
        :ref="el => { if (el) tabRefs[index] = el as HTMLButtonElement }"
        type="button"
        role="tab"
        class="console-tab"
        :class="{ 'is-active': active === tab.id }"
        :aria-selected="active === tab.id"
        aria-controls="console-panel"
        :tabindex="active === tab.id ? 0 : -1"
        @click="select(tab.id)"
        @keydown="move($event, index)"
      >
        <span class="console-tab-icon" aria-hidden="true">
          <LandingGlyph :name="tab.icon" class="size-4" />
        </span>
        <span class="console-tab-label">{{ tab.label }}</span>
      </button>
    </div>

    <div
      id="console-panel"
      class="console-panel"
      role="tabpanel"
      :aria-labelledby="`console-tab-${active}`"
    >
      <template v-if="active === 'request'">
        <div class="console-summary">
          <div class="console-summary-main">
            <span class="console-overline">Inbound request</span>
            <strong class="console-endpoint">
              <span class="console-method">POST</span>
              <span class="console-path">/v1/chat/completions</span>
            </strong>
          </div>
          <span class="console-pill console-pill--ok">
            <span class="console-pill-dot" aria-hidden="true" />
            Forwarded
          </span>
        </div>

        <div class="console-request">
          <div class="console-main">
            <div class="console-code-wrap">
              <div class="console-code-head">
                <span class="console-file">
                  <LandingGlyph name="file-json" class="size-3.5" />
                  request.http
                </span>
                <button
                  type="button"
                  class="console-copy"
                  :class="{ 'is-copied': copied }"
                  :aria-label="copied ? 'Request example copied' : 'Copy request example'"
                  title="Copy request example"
                  @click="copyRequest"
                >
                  <LandingGlyph :name="copied ? 'check' : 'copy'" class="size-3.5" />
                  {{ copied ? 'Copied' : 'Copy' }}
                </button>
              </div>

              <section class="console-code" tabindex="0" aria-label="Example request headers and body"><!-- NOSONAR --><!-- scrollable region: tabindex is the a11y-correct pattern (WCAG 2.1.1) per review on #1029 -->
                <div class="console-line">
                  <span class="console-ln">01</span>
                  <span><span class="console-key">Authorization</span><span class="console-punc">:</span> <span class="console-string">Bearer $IBEX_TOKEN</span></span>
                </div>
                <div class="console-line">
                  <span class="console-ln">02</span>
                  <span><span class="console-key">X-IBEX-Agent-ID</span><span class="console-punc">:</span> <span class="console-string">agent_support</span></span>
                </div>
                <div class="console-line">
                  <span class="console-ln">03</span>
                  <span><span class="console-key">Content-Type</span><span class="console-punc">:</span> <span class="console-string">application/json</span></span>
                </div>
                <div class="console-line console-line--gap">
                  <span class="console-ln">04</span>
                  <span><span class="console-punc">{</span></span>
                </div>
                <div class="console-line">
                  <span class="console-ln">05</span>
                  <span>  <span class="console-key">"model"</span><span class="console-punc">:</span> <span class="console-string">"gpt-4o"</span><span class="console-punc">,</span></span>
                </div>
                <div class="console-line">
                  <span class="console-ln">06</span>
                  <span>  <span class="console-key">"messages"</span><span class="console-punc">:</span> <span class="console-punc">[</span></span>
                </div>
                <div class="console-line">
                  <span class="console-ln">07</span>
                  <span>    <span class="console-punc">{</span></span>
                </div>
                <div class="console-line">
                  <span class="console-ln">08</span>
                  <span>      <span class="console-key">"role"</span><span class="console-punc">:</span> <span class="console-string">"user"</span><span class="console-punc">,</span></span>
                </div>
                <div class="console-line">
                  <span class="console-ln">09</span>
                  <span>      <span class="console-key">"content"</span><span class="console-punc">:</span> <span class="console-string">"hello"</span></span>
                </div>
                <div class="console-line">
                  <span class="console-ln">10</span>
                  <span>    <span class="console-punc">}</span></span>
                </div>
                <div class="console-line">
                  <span class="console-ln">11</span>
                  <span>  <span class="console-punc">]</span></span>
                </div>
                <div class="console-line">
                  <span class="console-ln">12</span>
                  <span><span class="console-punc">}</span></span>
                </div>
              </section>
            </div>

            <div class="console-response">
              <div class="console-response-bar">
                <span class="console-response-label">
                  <span class="console-response-dot" aria-hidden="true" />
                  Response
                </span>
                <span class="console-response-status">200 · text/event-stream</span>
              </div>
              <div class="console-response-body">
                <span class="console-key">data</span><span class="console-punc">:</span> <span class="console-string">{"choices":[{"delta":{"content":"..."}}]}</span>
              </div>
            </div>
          </div>

          <aside class="console-checks" aria-label="Boundary checks">
            <div class="console-checks-head">
              <span class="console-rail-label">Boundary checks</span>
              <span class="console-checks-count">4/4</span>
            </div>
            <ul>
              <li v-for="check in boundaryChecks" :key="check.name">
                <span class="console-check-icon" aria-hidden="true">
                  <LandingGlyph :name="check.icon" class="size-3.5" />
                </span>
                <span class="console-check-copy">
                  <span class="console-check-name">{{ check.name }}</span>
                  <span class="console-check-detail">{{ check.detail }}</span>
                </span>
              </li>
            </ul>
            <p class="console-checks-note">
              <LandingGlyph name="lock" class="size-4" />
              <span>Forwarded only after every check passes.</span>
            </p>
            <div class="console-tenant">
              <span class="console-tenant-label">
                <LandingGlyph name="fingerprint" class="size-3.5" />
                Tenant
              </span>
              <strong>org_a1f9</strong>
              <small>resolved from token</small>
            </div>
          </aside>
        </div>

        <div class="console-facts">
          <span><LandingGlyph name="circle-check" class="size-3.5" /><b>auth</b> verified</span>
          <span><LandingGlyph name="circle-check" class="size-3.5" /><b>tenant</b> from token</span>
          <span><LandingGlyph name="circle-check" class="size-3.5" /><b>body</b> unchanged</span>
        </div>
      </template>

      <template v-else-if="active === 'context'">
        <div class="console-summary">
          <div class="console-summary-main">
            <span class="console-overline">Context budget</span>
            <strong class="console-heading">Assemble before forward</strong>
          </div>
          <span class="console-pill">
            <span class="console-pill-dot" aria-hidden="true" />
            Example allocation
          </span>
        </div>

        <div class="budget">
          <div class="budget-head">
            <span class="console-rail-label">Token allocation</span>
            <span class="console-checks-count">100%</span>
          </div>
          <div class="budget-bar" aria-hidden="true">
            <span
              v-for="(segment, index) in budgetSegments"
              :key="segment.label"
              class="budget-segment"
              :class="`budget-segment--${index + 1}`"
              :style="{ width: segment.width }"
            />
          </div>
          <div class="budget-legend">
            <span v-for="(segment, index) in budgetSegments" :key="segment.label" class="budget-legend-item">
              <span class="budget-swatch" :class="`budget-swatch--${index + 1}`" aria-hidden="true" />
              <span>{{ segment.label }}</span>
              <b>{{ segment.value }}</b>
            </span>
          </div>
        </div>

        <div class="context-list">
          <div class="context-list-head">
            <span class="console-rail-label">Retrieved memories</span>
            <span class="console-checks-count">3</span>
          </div>
          <div v-for="row in contextRows" :key="row.id" class="context-row">
            <code>{{ row.id }}</code>
            <span>{{ row.detail }}</span>
            <span class="context-state" :class="{ 'is-held': row.state === 'held' }">{{ row.state }}</span>
          </div>
        </div>

        <div class="console-facts">
          <span><b>fallback</b> directive-only</span>
          <span><b>deadline</b> bounded</span>
        </div>
      </template>

      <template v-else>
        <div class="console-summary">
          <div class="console-summary-main">
            <span class="console-overline">Request trace</span>
            <strong class="console-heading">One request, inspectable</strong>
          </div>
          <span class="console-pill console-pill--ok">
            <span class="console-pill-dot" aria-hidden="true" />
            Local example
          </span>
        </div>

        <div class="trace-list">
          <div class="trace-list-head">
            <span class="console-rail-label">Request timeline</span>
            <span class="console-checks-count">5 steps</span>
          </div>
          <div v-for="row in traceRows" :key="row.step" class="trace-row">
            <span class="trace-marker" :class="`trace-marker--${row.state}`" aria-hidden="true">
              <LandingGlyph :name="row.icon" class="size-3.5" />
            </span>
            <span class="trace-step">{{ row.step }}</span>
            <span class="trace-detail">{{ row.detail }}</span>
            <span class="trace-state" :class="`trace-state--${row.state}`">{{ row.state }}</span>
          </div>
        </div>

        <div class="console-facts">
          <span><b>scope</b> local evidence</span>
          <span><b>claim</b> not a hosted SLO</span>
        </div>
      </template>
    </div>

    <div class="console-foot">
      <span><span class="console-foot-dot" aria-hidden="true" /> Tenant comes from the token</span>
      <NuxtLink to="/docs/architecture/request-lifecycle">
        Request lifecycle
        <LandingGlyph name="arrow-up-right" class="size-3" />
      </NuxtLink>
    </div>
  </div>
</template>

<style scoped>
.harness-console {
  display: flex;
  min-width: 0;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--site-line-strong);
  border-radius: 14px;
  background: var(--site-surface-strong);
  color: var(--site-ink);
  box-shadow:
    0 1px 0 rgb(255 255 255 / 0.7) inset,
    0 30px 70px -46px rgb(10 11 12 / 0.65);
}

.console-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1rem;
  min-height: 3.3rem;
  padding: 0.65rem 0.95rem;
  border-bottom: 1px solid var(--site-line);
  background: var(--site-surface);
  font-family: var(--font-mono);
  font-size: 0.65rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--site-muted);
}

.console-brand,
.console-state {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
}

.console-brand {
  color: var(--site-ink);
  font-weight: 600;
  letter-spacing: 0.12em;
}

.console-mark {
  width: 0.55rem;
  height: 0.55rem;
  border-radius: 999px;
  background: var(--site-signal);
  box-shadow: 0 0 0 5px color-mix(in srgb, var(--site-signal) 12%, transparent);
}

.console-state {
  padding: 0.34rem 0.58rem;
  border: 1px solid var(--site-line);
  border-radius: 999px;
  background: var(--site-surface-strong);
  font-size: 0.58rem;
  color: var(--site-muted);
}

.console-state-dot {
  width: 0.34rem;
  height: 0.34rem;
  border-radius: 999px;
  background: var(--site-signal);
}

.console-tabs {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.25rem;
  padding: 0.45rem 0.55rem;
  border-bottom: 1px solid var(--site-line);
  background: var(--site-surface);
}

.console-tab {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: center;
  gap: 0.55rem;
  padding: 0.62rem 0.75rem;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: var(--site-muted);
  text-align: left;
  transition: background-color 140ms ease, border-color 140ms ease, color 140ms ease, box-shadow 140ms ease;
}

.console-tab:hover {
  border-color: var(--site-line);
  background: var(--site-surface-strong);
  color: var(--site-ink);
}

.console-tab:focus-visible {
  outline: 2px solid var(--site-signal);
  outline-offset: -2px;
}

.console-tab.is-active {
  border-color: #0a0b0c;
  background: #0a0b0c;
  color: #f4f1e8;
  box-shadow: 0 10px 22px -18px rgb(10 11 12 / 0.9);
}

.console-tab-icon {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  color: var(--site-muted);
  transition: color 140ms ease;
}

.console-tab:hover .console-tab-icon,
.console-tab.is-active .console-tab-icon {
  color: #d8ff4f;
}

.console-tab-label {
  font-family: var(--font-mono);
  font-size: 0.74rem;
  font-weight: 600;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: inherit;
}

.console-panel {
  display: flex;
  min-height: 26rem;
  flex: 1;
  flex-direction: column;
  padding: 1.05rem;
}

.console-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem 1rem;
  padding-bottom: 0.95rem;
  border-bottom: 1px solid var(--site-line);
}

.console-summary-main {
  min-width: 0;
}

.console-overline {
  display: block;
  margin-bottom: 0.32rem;
  font-family: var(--font-mono);
  font-size: 0.6rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--site-muted);
}

.console-summary strong {
  display: block;
  font-family: var(--font-mono);
  font-size: 0.9rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--site-ink);
}

.console-endpoint {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.console-method {
  display: inline-flex;
  align-items: center;
  padding: 0.2rem 0.45rem;
  border-radius: 5px;
  background: #d8ff4f;
  color: #0a0b0c;
  font-size: 0.66rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  line-height: 1.2;
}

.console-path {
  overflow-wrap: anywhere;
}

/* Scoped to the summary so it outweighs .console-summary strong without !important. */
.console-summary .console-heading {
  font-size: 0.98rem;
  letter-spacing: -0.02em;
}

.console-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.32rem 0.58rem;
  border: 1px solid var(--site-line);
  border-radius: 999px;
  background: var(--site-surface-strong);
  font-family: var(--font-mono);
  font-size: 0.58rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--site-muted);
  white-space: nowrap;
}

.console-pill--ok {
  border-color: color-mix(in srgb, var(--site-signal) 34%, var(--site-line));
  background: color-mix(in srgb, #d8ff4f 24%, #fff);
  color: #3f6b00;
}

.console-pill-dot {
  width: 0.35rem;
  height: 0.35rem;
  border-radius: 999px;
  background: currentColor;
}

.console-request {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(11.5rem, 0.62fr);
  gap: 0.85rem;
  align-items: stretch;
  margin-top: 1rem;
}

.console-main {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.8rem;
}

.console-code-wrap {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--site-line);
  border-radius: 10px;
  background: var(--site-surface-strong);
}

.console-code-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  min-height: 2.55rem;
  padding: 0 0.55rem 0 0.75rem;
  border-bottom: 1px solid var(--site-line);
  background: var(--site-surface);
  font-family: var(--font-mono);
  font-size: 0.66rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--site-muted);
}

.console-file {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--site-ink);
  font-weight: 500;
}

.console-file :deep(svg) {
  color: var(--site-signal);
}

.console-copy {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  min-height: 1.9rem;
  padding: 0.28rem 0.55rem;
  border: 1px solid var(--site-line);
  border-radius: 6px;
  background: var(--site-surface-strong);
  font-family: var(--font-mono);
  font-size: 0.64rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--site-ink);
  transition: background-color 140ms ease, border-color 140ms ease, color 140ms ease;
}

.console-copy:hover {
  border-color: var(--site-signal);
  background: color-mix(in srgb, #d8ff4f 20%, #fff);
}

.console-copy.is-copied {
  border-color: var(--site-signal);
  background: color-mix(in srgb, #d8ff4f 30%, #fff);
  color: #3f6b00;
}

.console-code {
  overflow-x: auto;
  padding: 0.85rem 0 0.95rem;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  font-weight: 500;
  line-height: 1.9;
  scrollbar-color: var(--site-line-strong) transparent;
  scrollbar-width: thin;
}

.console-code:focus-visible {
  outline: 2px solid var(--site-signal);
  outline-offset: -2px;
}

.console-line {
  display: grid;
  grid-template-columns: 2.6rem minmax(0, 1fr);
  padding-right: 0.8rem;
  white-space: pre;
}

.console-line--gap {
  margin-top: 0.4rem;
}

.console-ln {
  padding-right: 0.6rem;
  font-size: 0.68rem;
  text-align: right;
  color: var(--site-muted);
  user-select: none;
}

.console-key { color: #6d28d9; font-weight: 600; }
.console-string { color: #3f7a00; }
.console-punc { color: #5f6b63; }

.console-response {
  overflow: hidden;
  border: 1px solid var(--site-line);
  border-radius: 10px;
  background: var(--site-surface-strong);
}

.console-response-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.35rem 0.75rem;
  padding: 0.5rem 0.7rem;
  border-bottom: 1px solid var(--site-line);
  background: var(--site-surface);
  font-family: var(--font-mono);
  font-size: 0.64rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--site-muted);
}

.console-response-label {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--site-ink);
  font-weight: 500;
}

.console-response-dot {
  width: 0.35rem;
  height: 0.35rem;
  border-radius: 999px;
  background: var(--site-signal);
}

.console-response-status {
  padding: 0.2rem 0.45rem;
  border-radius: 999px;
  background: color-mix(in srgb, #d8ff4f 22%, #fff);
  color: #3f6b00;
  font-size: 0.62rem;
  font-weight: 600;
}

.console-response-body {
  overflow-x: hidden;
  padding: 0.7rem 0.75rem;
  font-family: var(--font-mono);
  font-size: 0.72rem;
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.console-checks {
  display: flex;
  min-width: 0;
  flex-direction: column;
  padding: 0.75rem;
  border: 1px solid var(--site-line);
  border-radius: 10px;
  background: var(--site-surface);
}

.console-checks-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding-bottom: 0.55rem;
  border-bottom: 1px solid var(--site-line);
}

.console-rail-label {
  font-family: var(--font-mono);
  font-size: 0.62rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--site-ink);
}

.console-checks-count {
  padding: 0.16rem 0.36rem;
  border-radius: 999px;
  background: color-mix(in srgb, #d8ff4f 24%, #fff);
  font-family: var(--font-mono);
  font-size: 0.55rem;
  font-weight: 500;
  color: #3f6b00;
}

.console-checks ul {
  display: grid;
  gap: 0;
  margin: 0 0 0.65rem;
  padding: 0;
  list-style: none;
}

.console-checks li {
  display: grid;
  grid-template-columns: 1.4rem minmax(0, 1fr);
  gap: 0.5rem;
  align-items: start;
  padding: 0.65rem 0;
  border-top: 1px solid var(--site-line);
}

.console-checks li:first-child {
  border-top: 0;
}

.console-check-icon {
  display: grid;
  width: 1.55rem;
  height: 1.55rem;
  place-items: center;
  border: 1px solid color-mix(in srgb, var(--site-signal) 26%, var(--site-line));
  border-radius: 50%;
  background: color-mix(in srgb, #d8ff4f 24%, #fff);
  color: #3f6b00;
}

.console-check-copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.08rem;
}

.console-check-name {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--site-ink);
}

.console-check-detail {
  font-family: var(--font-mono);
  font-size: 0.64rem;
  line-height: 1.4;
  color: var(--site-muted);
}

.console-tenant {
  display: grid;
  gap: 0.18rem;
  margin-top: 0.65rem;
  padding: 0.6rem 0.65rem;
  border: 1px solid var(--site-line);
  border-radius: 8px;
  background: var(--site-surface-strong);
}

.console-checks-note {
  display: flex;
  align-items: flex-start;
  gap: 0.45rem;
  margin: auto 0 0;
  padding: 0.6rem 0.65rem;
  border: 1px dashed color-mix(in srgb, var(--site-signal) 28%, var(--site-line));
  border-radius: 8px;
  background: color-mix(in srgb, #d8ff4f 9%, #fff);
  font-family: var(--font-mono);
  font-size: 0.61rem;
  line-height: 1.5;
  color: var(--site-muted);
}

.console-checks-note :deep(svg) {
  flex: none;
  margin-top: 0.08rem;
  color: var(--site-signal);
}

.console-tenant-label {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-family: var(--font-mono);
  font-size: 0.6rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--site-muted);
}

.console-tenant-label :deep(svg) {
  color: var(--site-signal);
}

.console-tenant strong {
  font-family: var(--font-mono);
  font-size: 0.86rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--site-ink);
}

.console-tenant small {
  font-family: var(--font-mono);
  font-size: 0.6rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--site-muted);
}

.console-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: auto;
  padding-top: 0.9rem;
  border-top: 1px solid var(--site-line);
}

.console-facts span {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.3rem 0.5rem;
  border: 1px solid var(--site-line);
  border-radius: 6px;
  background: var(--site-surface);
  font-family: var(--font-mono);
  font-size: 0.63rem;
  letter-spacing: 0.02em;
  color: var(--site-muted);
}

.console-facts :deep(svg) {
  color: var(--site-signal);
}

.console-facts b {
  color: var(--site-ink);
  font-weight: 600;
}

.budget {
  margin-top: 1rem;
  padding: 0.8rem;
  border: 1px solid var(--site-line);
  border-radius: 10px;
  background: var(--site-surface-strong);
}

.budget-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.65rem;
}

.budget-bar {
  display: flex;
  gap: 3px;
  height: 1.1rem;
  overflow: hidden;
  border-radius: 6px;
}

.budget-segment {
  height: 100%;
}

.budget-segment--1 { background: #d8ff4f; }
.budget-segment--2 { background: color-mix(in srgb, var(--site-signal) 55%, #fff); }
.budget-segment--3 { background: var(--site-ink); }
.budget-segment--4 {
  border: 1px dashed var(--site-line-strong);
  background: transparent;
}

.budget-legend {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.45rem 0.85rem;
  margin-top: 0.7rem;
}

.budget-legend-item {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-family: var(--font-mono);
  font-size: 0.6rem;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--site-muted);
}

.budget-legend-item b {
  margin-left: auto;
  font-weight: 600;
  color: var(--site-ink);
}

.budget-swatch {
  width: 0.45rem;
  height: 0.45rem;
  flex: none;
  border-radius: 2px;
}

.budget-swatch--1 { background: #d8ff4f; }
.budget-swatch--2 { background: color-mix(in srgb, var(--site-signal) 55%, #fff); }
.budget-swatch--3 { background: var(--site-ink); }
.budget-swatch--4 {
  border: 1px dashed var(--site-line-strong);
  background: transparent;
}

.context-list {
  margin-top: 1rem;
  overflow: hidden;
  border: 1px solid var(--site-line);
  border-radius: 10px;
  background: var(--site-surface-strong);
}

.context-list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.6rem 0.75rem;
  border-bottom: 1px solid var(--site-line);
  background: var(--site-surface);
}

.context-row {
  display: grid;
  grid-template-columns: 5.5rem minmax(0, 1fr) auto;
  gap: 0.6rem;
  align-items: center;
  padding: 0.65rem 0.75rem;
  border-bottom: 1px solid var(--site-line);
  font-size: 0.78rem;
  line-height: 1.4;
}

.context-row:last-child {
  border-bottom: 0;
}

.context-row code {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 500;
  color: var(--site-signal);
}

.context-row > span:nth-child(2) {
  color: var(--site-muted);
}

.context-state {
  padding: 0.2rem 0.42rem;
  border-radius: 999px;
  background: color-mix(in srgb, #d8ff4f 24%, #fff);
  font-family: var(--font-mono);
  font-size: 0.55rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #3f6b00;
}

.context-state.is-held {
  background: color-mix(in srgb, var(--chart-amber) 14%, #fff);
  color: var(--chart-amber);
}

.trace-list {
  margin-top: 1rem;
  overflow: hidden;
  border: 1px solid var(--site-line);
  border-radius: 10px;
  background: var(--site-surface-strong);
}

.trace-list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.6rem 0.75rem;
  border-bottom: 1px solid var(--site-line);
  background: var(--site-surface);
}

.trace-row {
  display: grid;
  grid-template-columns: 1.4rem minmax(7rem, 0.9fr) minmax(0, 1.5fr) auto;
  gap: 0.6rem;
  align-items: center;
  padding: 0.7rem 0.75rem;
  border-bottom: 1px solid var(--site-line);
  font-size: 0.76rem;
  line-height: 1.4;
}

.trace-row:last-child {
  border-bottom: 0;
}

.trace-marker {
  display: grid;
  width: 1.4rem;
  height: 1.4rem;
  place-items: center;
  border-radius: 50%;
  background: color-mix(in srgb, #d8ff4f 22%, #fff);
  color: #3f6b00;
}

.trace-marker--live {
  background: color-mix(in srgb, var(--chart-amber) 16%, #fff);
  color: var(--chart-amber);
}

.trace-marker--async {
  background: var(--site-surface);
  color: var(--site-muted);
}

.trace-step {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  font-weight: 500;
  color: var(--site-ink);
}

.trace-detail {
  color: var(--site-muted);
}

.trace-state {
  padding: 0.2rem 0.42rem;
  border-radius: 999px;
  background: color-mix(in srgb, #d8ff4f 24%, #fff);
  font-family: var(--font-mono);
  font-size: 0.55rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #3f6b00;
}

.trace-state--live {
  background: color-mix(in srgb, var(--chart-amber) 14%, #fff);
  color: var(--chart-amber);
}

.trace-state--async {
  background: var(--site-surface);
  color: var(--site-muted);
}

.console-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.4rem 1rem;
  padding: 0.75rem 0.95rem;
  border-top: 1px solid var(--site-line);
  background: var(--site-surface);
  font-family: var(--font-mono);
  font-size: 0.6rem;
  letter-spacing: 0.03em;
  color: var(--site-muted);
}

.console-foot > span,
.console-foot a {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}

.console-foot a {
  color: var(--site-ink);
  transition: color 140ms ease;
}

.console-foot a:hover {
  color: var(--site-signal);
}

.console-foot-dot {
  width: 0.34rem;
  height: 0.34rem;
  border-radius: 999px;
  background: var(--site-signal);
}

@media (max-width: 1180px) {
  .console-code {
    font-size: 0.76rem;
  }

  .console-line {
    grid-template-columns: 2.45rem minmax(0, 1fr);
  }

  .console-ln {
    font-size: 0.65rem;
  }
}

@media (max-width: 620px) {
  .console-request {
    grid-template-columns: 1fr;
  }

  .console-tenant {
    margin-top: 0.7rem;
  }
}

@media (max-width: 520px) {
  .console-bar {
    min-height: 3rem;
    padding: 0.55rem 0.75rem;
  }

  .console-panel {
    min-height: 23rem;
    padding: 0.8rem;
  }

  .console-tabs {
    gap: 0.3rem;
    padding: 0.45rem;
  }

  .console-tab {
    gap: 0.4rem;
    padding: 0.45rem 0.5rem;
  }

  .console-code {
    font-size: 0.72rem;
  }

  .console-line {
    grid-template-columns: 2.25rem minmax(0, 1fr);
  }

  .console-response-body {
    font-size: 0.68rem;
  }

  .budget-legend {
    grid-template-columns: 1fr;
  }

  .context-row {
    grid-template-columns: 1fr auto;
  }

  .context-row > span:nth-child(2) {
    grid-column: 1 / -1;
    grid-row: 2;
  }

  .trace-row {
    grid-template-columns: 1.4rem minmax(0, 1fr) auto;
  }

  .trace-marker {
    grid-column: 1;
    grid-row: 1;
  }

  .trace-step {
    grid-column: 2;
    grid-row: 1;
  }

  .trace-state {
    grid-column: 3;
    grid-row: 1;
  }

  .trace-detail {
    grid-column: 2 / -1;
    grid-row: 2;
  }

  .console-facts span {
    font-size: 0.6rem;
  }
}
</style>
