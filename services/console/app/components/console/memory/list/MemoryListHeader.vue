<script setup lang="ts">
import { onBeforeUnmount, ref } from "vue"
import { Download, Ellipsis, FileJson, FileSpreadsheet, FileText, Link2, X } from "@lucide/vue"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import MemoryJsonView from "@/components/console/memory/primitives/MemoryJsonView.vue"
import type { PreviewMemory } from "@/lib/memory-preview"

const props = defineProps<{
  total: number
  agentCount: number
  records: PreviewMemory[]
}>()

const header = ref<InstanceType<typeof ConsolePageHeader> | null>(null)
const rawDialog = ref<HTMLDialogElement | null>(null)
const copiedKey = ref("")
let copyTimer: ReturnType<typeof setTimeout> | null = null
let lastDialogTrigger: HTMLElement | null = null

const aboutNotes = [
  {
    lead: "Inclusion is not influence.",
    body: "A retrieval that placed a memory in context does not measure whether the answer used it.",
  },
  {
    lead: "A missing finding is not proof.",
    body: "An empty safety cell means no finding is recorded, not that the memory is certified safe.",
  },
  {
    lead: "Filters apply locally.",
    body: `Filtering, sorting, and grouping run over the ${props.total} illustrative rows in this browser and stay in the URL.`,
  },
]

function markCopied(key: string): void {
  copiedKey.value = key
  if (copyTimer) clearTimeout(copyTimer)
  copyTimer = setTimeout(() => {
    copiedKey.value = ""
  }, 1600)
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
  markCopied(key)
}

async function copyLink(): Promise<void> {
  if (!import.meta.client) return
  await copyValue(window.location.href, "link")
}

function downloadText(filename: string, content: string, type: string): void {
  if (!import.meta.client) return
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function csvCell(value: unknown): string {
  const text = value === null || value === undefined ? "" : String(value)
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

function exportCsv(): void {
  const header = [
    "id",
    "content",
    "category",
    "status",
    "agent",
    "agent_id",
    "visibility",
    "source",
    "confidence",
    "usefulness",
    "retrieval_count",
    "last_retrieved_at",
    "pinned",
    "tags",
    "valid_from",
    "valid_until",
  ]
  const rows = props.records.map((memory) =>
    [
      memory.id,
      memory.content,
      memory.category,
      memory.status,
      memory.agent,
      memory.agentId,
      memory.visibility,
      memory.source,
      memory.confidence,
      memory.usefulness,
      memory.retrievalCount,
      memory.lastRetrievedAt,
      memory.pinned,
      memory.tags.join("|"),
      memory.validFrom,
      memory.validUntil,
    ]
      .map(csvCell)
      .join(","),
  )
  downloadText("ibex-memories-preview.csv", [header.join(","), ...rows].join("\n"), "text/csv;charset=utf-8")
}

function exportJson(): void {
  downloadText("ibex-memories-preview.json", JSON.stringify(props.records, null, 2), "application/json")
}

function openRawJson(event: Event): void {
  lastDialogTrigger = event.currentTarget instanceof HTMLElement ? event.currentTarget : null
  rawDialog.value?.showModal()
}

function closeRawJson(): void {
  rawDialog.value?.close()
  lastDialogTrigger?.focus()
}

function onRawBackdrop(event: MouseEvent): void {
  if (event.target === rawDialog.value) closeRawJson()
}

onBeforeUnmount(() => {
  if (copyTimer) clearTimeout(copyTimer)
})
</script>

<template>
  <ConsolePageHeader
    ref="header"
    title="Memories"
    definition="What the organization stored, where it came from, and how retrieval and safety state changed."
    state="illustrative"
    :verdict="`Preview renders ${total} illustrative memories across ${agentCount} agents. Content reads, retrieval history, and conflict writes are not connected.`"
    contract="operator.memories.list.v1 + retrieval history [NEEDS-BACKEND]"
    scope="org_demo_42 · all scopes"
    range="Last 48 hours"
    coverage="0% live · illustrative only"
    :notes="aboutNotes"
  >
    <template #actions>
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <button type="button" class="ix-button-secondary" aria-label="Export memories">
            <Download :size="13" :stroke-width="1.8" aria-hidden="true" />
            Export
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" class="w-52 p-1.5">
          <DropdownMenuLabel class="px-2 py-1 text-[0.6875rem] font-medium text-fg-3">
            {{ records.length }} filtered {{ records.length === 1 ? "record" : "records" }}
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem class="gap-2 py-1.5 text-xs" @select="exportCsv">
            <FileSpreadsheet :size="13" :stroke-width="1.8" aria-hidden="true" />
            Export CSV
          </DropdownMenuItem>
          <DropdownMenuItem class="gap-2 py-1.5 text-xs" @select="exportJson">
            <FileJson :size="13" :stroke-width="1.8" aria-hidden="true" />
            Export JSON
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <button type="button" class="console-icon-button" aria-label="More memory actions">
            <Ellipsis :size="15" :stroke-width="1.8" aria-hidden="true" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" class="w-56 p-1.5">
          <DropdownMenuItem class="gap-2 py-1.5 text-xs" @select="copyLink">
            <Link2 :size="13" :stroke-width="1.8" aria-hidden="true" />
            Copy link to this view
          </DropdownMenuItem>
          <DropdownMenuItem class="gap-2 py-1.5 text-xs" @select="header?.openAbout()">
            <FileText :size="13" :stroke-width="1.8" aria-hidden="true" />
            View contract
          </DropdownMenuItem>
          <DropdownMenuItem class="gap-2 py-1.5 text-xs" @select="openRawJson">
            <FileJson :size="13" :stroke-width="1.8" aria-hidden="true" />
            Raw JSON
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </template>
  </ConsolePageHeader>

  <dialog
    ref="rawDialog"
    class="w-[min(48rem,calc(100vw-1.5rem))] max-w-none rounded-lg border border-line bg-overlay p-0 text-fg-1 shadow-2xl backdrop:bg-canvas/70"
    aria-label="Raw preview records"
    @click="onRawBackdrop"
    @close="lastDialogTrigger?.focus()"
  >
    <div class="flex items-start justify-between gap-3 border-b border-line-subtle px-4 py-3">
      <div>
        <p class="text-sm font-semibold text-fg-1">Raw preview records</p>
        <p class="mt-0.5 text-xs text-fg-3">{{ records.length }} filtered illustrative {{ records.length === 1 ? "record" : "records" }} · read-only</p>
      </div>
      <button
        type="button"
        class="inline-flex size-7 items-center justify-center rounded-md text-fg-3 transition-colors hover:bg-surface-2 hover:text-fg-1"
        aria-label="Close raw JSON"
        @click="closeRawJson"
      >
        <X :size="15" :stroke-width="1.8" aria-hidden="true" />
      </button>
    </div>
    <div class="ix-scroll max-h-[70dvh] overflow-auto p-4">
      <MemoryJsonView :value="records" />
    </div>
  </dialog>
</template>
