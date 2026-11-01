<script setup lang="ts">
import { computed } from "vue"
import { ChevronDown, ChevronLeft, ChevronRight } from "@lucide/vue"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type { PolicySnapshot } from "@/lib/policy-preview"
import { formatGovernStamp, shortDigest } from "@/lib/govern-format"

const props = withDefaults(
  defineProps<{
    snapshots: PolicySnapshot[]
    modelValue: string
    label?: string
  }>(),
  { label: "Snapshot" },
)

const emit = defineEmits<{ "update:modelValue": [value: string] }>()

const index = computed(() => props.snapshots.findIndex((snapshot) => snapshot.id === props.modelValue))
const current = computed(() => (index.value >= 0 ? props.snapshots[index.value]! : null))
const newer = computed(() => (index.value > 0 ? props.snapshots[index.value - 1]! : null))
const older = computed(() => (index.value >= 0 ? props.snapshots[index.value + 1] ?? null : null))

function select(id: string): void {
  emit("update:modelValue", id)
}
</script>

<template>
  <div class="inline-flex min-w-0 items-center gap-1">
    <span class="sr-only">{{ label }} picker</span>
    <button
      type="button"
      class="inline-flex size-8 items-center justify-center rounded-md border border-line-subtle bg-surface-1 text-fg-3 transition-colors hover:border-line hover:text-fg-1 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
      :disabled="!older"
      :aria-label="older ? `Earlier snapshot: ${older.id} effective ${formatGovernStamp(older.effectiveFrom)}` : 'Oldest snapshot selected'"
      @click="older && select(older.id)"
    >
      <ChevronLeft :size="14" :stroke-width="1.9" aria-hidden="true" />
    </button>

    <DropdownMenu>
      <DropdownMenuTrigger as-child>
        <button
          type="button"
          class="inline-flex h-8 min-w-0 items-center gap-2 rounded-md border border-line-subtle bg-surface-1 px-2.5 text-xs text-fg-2 transition-colors hover:border-line hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
          :aria-label="current ? `${label}: ${current.id} effective ${formatGovernStamp(current.effectiveFrom)}` : `${label}: none`"
        >
          <span v-if="current" class="truncate font-mono text-[0.6875rem] font-medium text-fg-1">{{ current.id }}</span>
          <span v-else class="font-medium text-fg-2">No snapshot</span>
          <ChevronDown :size="11" :stroke-width="1.9" class="shrink-0 text-fg-3" aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" class="w-80 p-1.5">
        <DropdownMenuLabel class="px-2 py-1 text-[0.6875rem] font-medium text-fg-3">
          {{ label }} · newest first
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          v-for="snapshot in snapshots"
          :key="snapshot.id"
          class="flex flex-col items-stretch gap-0.5 py-1.5 text-xs"
          @select="select(snapshot.id)"
        >
          <span class="flex items-center justify-between gap-2">
            <span class="font-mono font-medium text-fg-1">{{ snapshot.id }}</span>
            <span v-if="snapshot.id === modelValue" class="text-[0.625rem] text-accent-memory">Selected</span>
          </span>
          <span class="flex items-center justify-between gap-2 text-[0.6875rem] text-fg-3">
            <span>Effective {{ formatGovernStamp(snapshot.effectiveFrom) }}</span>
            <span class="font-mono">{{ shortDigest(snapshot.digest) }}</span>
          </span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>

    <button
      type="button"
      class="inline-flex size-8 items-center justify-center rounded-md border border-line-subtle bg-surface-1 text-fg-3 transition-colors hover:border-line hover:text-fg-1 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
      :disabled="!newer"
      :aria-label="newer ? `Later snapshot: ${newer.id} effective ${formatGovernStamp(newer.effectiveFrom)}` : 'Newest snapshot selected'"
      @click="newer && select(newer.id)"
    >
      <ChevronRight :size="14" :stroke-width="1.9" aria-hidden="true" />
    </button>
  </div>
</template>
