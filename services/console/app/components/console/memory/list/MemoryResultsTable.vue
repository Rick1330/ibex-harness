<script setup lang="ts">
import { computed } from "vue"
import { ArrowDown, ArrowUp, ChevronsUpDown } from "@lucide/vue"
import type { MemorySortDirection, MemorySortKey, MemoryOptionalColumn } from "@/lib/memory-list-query"
import type { MemoryGroup as GroupedMemories } from "@/lib/memory-list"
import MemoryTableRow from "./MemoryTableRow.vue"

const props = defineProps<{
  groups: GroupedMemories[]
  selectedIds: Set<string>
  activeId: string
  density: "comfortable" | "compact"
  columns: MemoryOptionalColumn[]
  showTags: boolean
  query: string
  returnTo: string
  sort: MemorySortKey
  direction: MemorySortDirection
  allSelected: boolean
  someSelected: boolean
}>()

const emit = defineEmits<{
  open: [id: string]
  peek: [id: string]
  toggle: [id: string]
  toggleAll: []
  toggleMany: [ids: string[], selected: boolean]
  sort: [key: MemorySortKey]
}>()

const totalRows = computed(() => props.groups.reduce((total, group) => total + group.rows.length, 0))
const columnCount = computed(() => 7 + props.columns.length)
const grouped = computed(() => props.groups.length > 1 || Boolean(props.groups[0]?.label))

const sortableColumns: Array<{ key: MemorySortKey; label: string }> = [
  { key: "content", label: "Memory" },
  { key: "confidence", label: "Confidence" },
  { key: "usefulness", label: "Usefulness" },
  { key: "retrievals", label: "Retrievals" },
  { key: "updated", label: "Updated" },
]

function ariaSort(key: MemorySortKey): "ascending" | "descending" | "none" {
  if (props.sort !== key) return "none"
  return props.direction === "asc" ? "ascending" : "descending"
}

function sortIcon(key: MemorySortKey) {
  if (props.sort !== key) return ChevronsUpDown
  return props.direction === "asc" ? ArrowUp : ArrowDown
}

function groupSelection(group: GroupedMemories): boolean {
  return group.rows.length > 0 && group.rows.every((memory) => props.selectedIds.has(memory.id))
}

const optionalHeaderLabel: Record<MemoryOptionalColumn, string> = {
  source: "Source",
  lineage: "Lineage",
  validity: "Valid until",
  memoryId: "Memory ID",
  agentId: "Agent ID",
  sessionId: "Session",
  visibility: "Scope",
}
</script>

<template>
  <div class="ix-memory-table-scroll overflow-x-auto">
    <table class="ix-memory-table w-full min-w-[60rem] table-fixed border-collapse" aria-label="Memory table">
      <colgroup>
        <col style="width: 2.25rem" >
        <col >
        <col class="col-flags" >
        <template v-for="column in columns" :key="column">
          <col :class="`col-${column}`" >
        </template>
        <col class="col-confidence" >
        <col class="col-usefulness" >
        <col class="col-retrievals" >
        <col class="col-updated" >
      </colgroup>
      <thead>
        <tr class="h-8 border-b border-line">
          <th scope="col" class="pl-2">
            <input
              type="checkbox"
              class="size-3.5 cursor-pointer rounded border-line accent-[var(--ix-memory)]"
              :checked="allSelected"
              :indeterminate="someSelected && !allSelected"
              aria-label="Select all visible memories"
              @change="emit('toggleAll')"
            >
          </th>
          <th scope="col" class="pl-1.5 text-left" :aria-sort="ariaSort('content')">
            <button
              type="button"
              class="inline-flex h-full w-full items-center gap-1 rounded px-1 text-xs font-medium text-fg-3 transition-colors hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
              @click="emit('sort', 'content')"
            >
              Memory
              <component :is="sortIcon('content')" :size="10" :stroke-width="2" aria-hidden="true" />
            </button>
          </th>
          <th scope="col" class="px-2 text-left">
            <span class="text-xs font-medium text-fg-3">Flags</span>
            <span class="sr-only">Only exceptions are shown</span>
          </th>

          <th
            v-for="column in columns"
            :key="column"
            scope="col"
            class="px-2 text-left text-xs font-medium text-fg-3"
            :aria-sort="column === 'validity' ? ariaSort('validity') : undefined"
          >
            <button
              v-if="column === 'validity'"
              type="button"
              class="inline-flex h-full w-full items-center gap-1 rounded px-1 text-xs font-medium text-fg-3 transition-colors hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
              @click="emit('sort', 'validity')"
            >
              {{ optionalHeaderLabel[column] }}
              <component :is="sortIcon('validity')" :size="10" :stroke-width="2" aria-hidden="true" />
            </button>
            <span v-else>{{ optionalHeaderLabel[column] }}</span>
          </th>

          <th
            v-for="column in sortableColumns.filter((entry) => entry.key !== 'content')"
            :key="column.key"
            scope="col"
            class="px-2 text-right"
            :aria-sort="ariaSort(column.key)"
          >
            <button
              type="button"
              class="inline-flex h-full w-full items-center justify-end gap-1 rounded px-1 text-xs font-medium text-fg-3 transition-colors hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
              @click="emit('sort', column.key)"
            >
              {{ column.label }}
              <component :is="sortIcon(column.key)" :size="10" :stroke-width="2" aria-hidden="true" />
            </button>
          </th>
        </tr>
      </thead>

      <tbody v-for="group in groups" :key="group.key">
        <tr v-if="grouped" class="ix-memory-group-row h-8 bg-surface-2/70">
          <th scope="colgroup" :colspan="columnCount" class="px-2 py-1 text-left">
            <span class="inline-flex items-center gap-2 text-[0.6875rem] font-medium text-fg-2">
              <input
                type="checkbox"
                class="size-3 cursor-pointer rounded border-line accent-[var(--ix-memory)]"
                :checked="groupSelection(group)"
                :aria-label="`Select all in ${group.label}`"
                @click.stop
                @change="emit('toggleMany', group.rows.map((memory) => memory.id), !groupSelection(group))"
              >
              {{ group.label }}
              <span class="font-mono text-[0.625rem] text-fg-3 tabular-nums">{{ group.rows.length }}</span>
            </span>
          </th>
        </tr>

        <MemoryTableRow
          v-for="memory in group.rows"
          :key="memory.id"
          :memory="memory"
          :selected="selectedIds.has(memory.id)"
          :active="activeId === memory.id"
          :density="density"
          :columns="columns"
          :show-tags="showTags"
          :query="query"
          :return-to="returnTo"
          @open="emit('open', $event)"
          @peek="emit('peek', $event)"
          @toggle="emit('toggle', $event)"
        />
      </tbody>
    </table>
    <span class="sr-only" aria-live="polite">
      {{ totalRows }} {{ totalRows === 1 ? "memory" : "memories" }} shown
    </span>
  </div>
</template>

<style scoped>
.ix-memory-table .col-flags {
  width: 11.25rem;
}
.ix-memory-table .col-source {
  width: 6.5rem;
}
.ix-memory-table .col-lineage {
  width: 8.5rem;
}
.ix-memory-table .col-validity {
  width: 5.5rem;
}
.ix-memory-table .col-memoryId {
  width: 7rem;
}
.ix-memory-table .col-agentId {
  width: 7.5rem;
}
.ix-memory-table .col-sessionId {
  width: 8rem;
}
.ix-memory-table .col-visibility {
  width: 6rem;
}
.ix-memory-table .col-confidence,
.ix-memory-table .col-usefulness {
  width: 6rem;
}
.ix-memory-table .col-retrievals {
  width: 8.75rem;
}
.ix-memory-table .col-updated {
  width: 5.5rem;
}

.ix-memory-table thead th {
  background: var(--ix-surface);
  vertical-align: middle;
}

@media (max-width: 1535px) {
  .ix-memory-table .col-flags {
    width: 10.625rem;
  }
  .ix-memory-table .col-confidence,
  .ix-memory-table .col-usefulness {
    width: 5.25rem;
  }
  .ix-memory-table .col-retrievals {
    width: 7.5rem;
  }
  .ix-memory-table .col-updated {
    width: 4.75rem;
  }
}

.ix-memory-table tbody + tbody tr:first-child td {
  border-top: 1px solid var(--ix-line-subtle);
}
</style>
