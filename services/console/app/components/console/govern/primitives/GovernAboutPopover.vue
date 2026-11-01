<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { Check, ChevronDown, Copy, Info, Lock } from "@lucide/vue"

type DataSourceState = "live" | "partial" | "illustrative"

const props = withDefaults(
  defineProps<{
    verdict: string
    contract: string
    scope: string
    range: string
    /** Legacy boolean kept for existing pages. Prefer `state`. */
    live?: boolean
    state?: DataSourceState
    coverage?: string
    phase?: string
    retention?: string
    request?: string | null
    /** Defaults to the standard, non-negotiable claim. */
    claim?: string
    observed?: string | null
    notes?: { lead: string; body: string }[]
  }>(),
  {
    live: false,
    state: undefined,
    coverage: "",
    phase: "",
    retention: undefined,
    request: undefined,
    claim: "No audit, billing, or deletion claim.",
    observed: undefined,
    notes: () => [],
  },
)

const root = ref<HTMLDetailsElement | null>(null)
const copied = ref("")
let timer: ReturnType<typeof setTimeout> | null = null

const resolved = computed<DataSourceState>(() => props.state ?? (props.live ? "live" : "illustrative"))

const badge = computed(() => {
  switch (resolved.value) {
    case "live":
      return { label: "LIVE", tone: "border-transparent bg-transparent text-ok" }
    case "partial":
      return { label: "PARTIAL", tone: "border-warn/40 bg-transparent text-warn" }
    default:
      return { label: "ILLUSTRATIVE", tone: "border-transparent bg-transparent text-warn" }
  }
})

const subtitle = computed(() => {
  switch (resolved.value) {
    case "live":
      return "Live operator data"
    case "partial":
      return "Partly connected · some values stay illustrative"
    default:
      return "Illustrative preview · not live operator data"
  }
})

const observedValue = computed(() => {
  if (props.observed) return props.observed
  switch (resolved.value) {
    case "live":
      return "Live operator data"
    case "partial":
      return "Partial · see page caveats"
    default:
      return "None"
  }
})

const contractRows = computed(() => {
  const rows = [
    { key: "scope", label: "Scope", value: props.scope },
    { key: "range", label: "Range", value: props.range },
    { key: "source", label: "Source", value: props.contract },
    { key: "observed", label: "Observed", value: observedValue.value },
  ]
  if (props.retention) rows.push({ key: "retention", label: "Retention", value: props.retention })
  if (props.request) rows.push({ key: "request", label: "Request", value: props.request })
  rows.push({ key: "access", label: "Access", value: "Read-only" })
  return rows
})

function open(): void {
  if (root.value) root.value.open = true
}

function onPointerDown(event: PointerEvent): void {
  if (!root.value?.open) return
  if (event.target instanceof Node && !root.value.contains(event.target)) root.value.open = false
}

onMounted(() => {
  document.addEventListener("pointerdown", onPointerDown)
  document.addEventListener("keydown", onKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onPointerDown)
  document.removeEventListener("keydown", onKeydown)
})

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape" && root.value?.open) {
    event.preventDefault()
    root.value.open = false
    root.value.querySelector<HTMLElement>("summary")?.focus()
  }
}

async function copyValue(value: string, key: string): Promise<void> {
  if (!import.meta.client) return
  try {
    await navigator.clipboard.writeText(value)
  } catch {
    const area = document.createElement("textarea")
    area.value = value
    area.setAttribute("readonly", "")
    area.style.position = "fixed"
    area.style.opacity = "0"
    document.body.appendChild(area)
    area.select()
    document.execCommand("copy")
    area.remove()
  }
  copied.value = key
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    copied.value = ""
  }, 1_600)
}

defineExpose({ open })
</script>

<template>
  <details ref="root" class="relative min-w-0">
    <summary
      class="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-md text-xs leading-4 text-fg-3 transition-colors hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent [&::-webkit-details-marker]:hidden"
      aria-label="About this data"
    >
      <Info :size="12" :stroke-width="1.75" aria-hidden="true" />
      <span>About this data</span>
      <ChevronDown :size="11" :stroke-width="1.9" class="details-open transition-transform" aria-hidden="true" />
    </summary>

    <div
      class="absolute right-0 top-[calc(100%+0.5rem)] z-50 w-[28rem] rounded-lg border border-line bg-overlay p-4 text-left shadow-2xl max-sm:fixed max-sm:inset-x-3 max-sm:top-auto max-sm:bottom-3 max-sm:w-auto"
      role="dialog"
      aria-label="About this data"
    >
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <p class="text-sm font-semibold text-fg-1">About this data</p>
          <p class="mt-0.5 text-xs leading-4 text-fg-3">{{ subtitle }}</p>
        </div>
        <span
          class="inline-flex h-5.5 shrink-0 items-center rounded-full border px-2 font-mono text-[0.625rem] leading-none"
          :class="badge.tone"
        >{{ badge.label }}</span>
      </div>

      <p class="mt-3 rounded-lg border border-line-subtle bg-surface-2 p-2.5 text-xs leading-5 text-fg-2">
        {{ verdict }}
      </p>

      <dl class="mt-3 space-y-1.5 border-t border-line-subtle pt-3">
        <div v-for="row in contractRows" :key="row.key" class="flex items-start gap-2">
          <dt class="w-16 shrink-0 pt-0.5 text-[0.6875rem] text-fg-3">{{ row.label }}</dt>
          <dd class="flex min-w-0 flex-1 items-start gap-1.5">
            <code class="min-w-0 flex-1 break-words font-mono text-[0.6875rem] leading-4 text-fg-2">{{ row.value }}</code>
            <button
              type="button"
              class="inline-flex size-5 shrink-0 items-center justify-center rounded text-fg-3 transition-colors hover:bg-surface-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent"
              :aria-label="`Copy ${row.label}`"
              @click="copyValue(row.value, row.key)"
            >
              <Check v-if="copied === row.key" :size="11" :stroke-width="2" class="text-ok" aria-hidden="true" />
              <Copy v-else :size="11" :stroke-width="1.8" aria-hidden="true" />
            </button>
          </dd>
        </div>
      </dl>

      <ul v-if="notes.length" class="mt-3 space-y-2 border-t border-line-subtle pt-3 text-xs leading-4 text-fg-2">
        <li v-for="note in notes" :key="note.lead">
          <span class="font-medium text-fg-1">{{ note.lead }}</span>
          {{ note.body }}
        </li>
      </ul>

      <p class="mt-3 flex items-start gap-1.5 border-t border-line-subtle pt-3 text-xs leading-4 text-fg-2">
        <Info :size="12" :stroke-width="1.8" class="mt-0.5 shrink-0 text-fg-3" aria-hidden="true" />
        <span>{{ claim }}</span>
      </p>

      <div class="mt-3 flex items-start gap-1.5 border-t border-line-subtle pt-3 text-xs leading-4 text-fg-3">
        <Lock :size="12" :stroke-width="1.8" class="mt-0.5 shrink-0" aria-hidden="true" />
        <span>Read-only console. Promotion, approval, rollback, and publication require a privileged write contract.</span>
      </div>

      <div
        v-if="coverage || phase"
        class="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-line-subtle pt-3"
      >
        <span class="font-mono text-[0.625rem] text-fg-3">{{ coverage }}</span>
        <span class="font-mono text-[0.625rem] text-fg-3">{{ phase }}</span>
      </div>
    </div>
  </details>
</template>

<style scoped>
details[open] > summary .details-open {
  transform: rotate(180deg);
}
</style>
