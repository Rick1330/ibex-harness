<script setup lang="ts">
import { computed } from "vue"
import { splitDiffRows, type DiffOp, type SectionDiff } from "@/lib/govern-diff"

const props = withDefaults(
  defineProps<{
    sections: SectionDiff[]
    mode?: "sections" | "unified" | "split"
    fromLabel?: string
    toLabel?: string
  }>(),
  { mode: "sections", fromLabel: "Before", toLabel: "After" },
)

const visible = computed(() => props.sections)

function marker(line: DiffOp | null): string {
  if (!line) return ""
  if (line.type === "added") return "+"
  if (line.type === "removed") return "−"
  return ""
}

function rows(section: SectionDiff) {
  return splitDiffRows(section.lines)
}
</script>

<template>
  <div v-if="visible.length === 0" class="rounded-lg border border-dashed border-line-subtle bg-surface-1/40 px-4 py-6 text-center text-xs text-fg-3">
    No sections to compare.
  </div>

  <div v-else-if="mode === 'unified'" class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
    <div v-for="section in visible" :key="section.id">
      <div class="flex items-center justify-between gap-2 border-y border-line-subtle bg-raised/70 px-3 py-1.5 first:border-t-0">
        <span class="text-xs font-medium text-fg-2">{{ section.label }}</span>
        <span class="font-mono text-[0.625rem] text-fg-3">
          <template v-if="section.changed">+{{ section.added }} −{{ section.removed }}</template>
          <template v-else>unchanged</template>
        </span>
      </div>
      <div v-for="(line, index) in section.lines" :key="`${section.id}-${index}`" class="ix-diff-line" :data-kind="line.type">
        <span class="ix-diff-mark" aria-hidden="true">{{ marker(line) }}</span>
        <span class="min-w-0">
          <template v-if="line.tokens">
            <span
              v-for="(token, tokenIndex) in line.tokens"
              :key="tokenIndex"
              :class="token.type === 'added' ? 'ix-diff-word-add' : token.type === 'removed' ? 'ix-diff-word-remove' : undefined"
            >{{ token.text }}</span>
          </template>
          <template v-else>{{ line.text }}</template>
        </span>
        <span v-if="line.type !== 'same'" class="sr-only">{{ line.type === 'added' ? 'Added line' : 'Removed line' }}</span>
      </div>
    </div>
  </div>

  <div v-else-if="mode === 'split'" class="space-y-3">
    <section v-for="section in visible" :key="section.id" class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
      <div class="flex items-center justify-between gap-2 border-b border-line-subtle bg-raised/70 px-3 py-1.5">
        <span class="text-xs font-medium text-fg-2">{{ section.label }}</span>
        <span class="font-mono text-[0.625rem] text-fg-3">
          <template v-if="section.changed">+{{ section.added }} −{{ section.removed }}</template>
          <template v-else>unchanged</template>
        </span>
      </div>
      <div class="grid grid-cols-2 gap-x-2 border-b border-line-subtle bg-surface-2/60 px-3 py-1 text-[0.625rem] font-medium text-fg-3">
        <span>{{ fromLabel }}</span>
        <span>{{ toLabel }}</span>
      </div>
      <div v-for="(row, index) in rows(section)" :key="`${section.id}-${index}`" class="grid grid-cols-2 gap-x-2">
        <div v-if="row.left" class="ix-diff-line !px-2" :data-kind="row.left.type">
          <span class="ix-diff-mark" aria-hidden="true">{{ marker(row.left) }}</span>
          <span class="min-w-0">
            <template v-if="row.left.tokens">
              <span
                v-for="(token, tokenIndex) in row.left.tokens"
                :key="tokenIndex"
                :class="token.type === 'removed' ? 'ix-diff-word-remove' : undefined"
              >{{ token.text }}</span>
            </template>
            <template v-else>{{ row.left.text }}</template>
          </span>
        </div>
        <div v-else class="ix-diff-line !px-2" data-kind="empty" aria-hidden="true" />
        <div v-if="row.right" class="ix-diff-line !px-2" :data-kind="row.right.type">
          <span class="ix-diff-mark" aria-hidden="true">{{ marker(row.right) }}</span>
          <span class="min-w-0">
            <template v-if="row.right.tokens">
              <span
                v-for="(token, tokenIndex) in row.right.tokens"
                :key="tokenIndex"
                :class="token.type === 'added' ? 'ix-diff-word-add' : undefined"
              >{{ token.text }}</span>
            </template>
            <template v-else>{{ row.right.text }}</template>
          </span>
        </div>
        <div v-else class="ix-diff-line !px-2" data-kind="empty" aria-hidden="true" />
      </div>
    </section>
  </div>

  <div v-else class="space-y-3">
    <section v-for="section in visible" :key="section.id" class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
      <div class="flex items-center justify-between gap-2 border-b border-line-subtle bg-raised/70 px-3 py-1.5">
        <span class="text-xs font-medium text-fg-2">{{ section.label }}</span>
        <span class="font-mono text-[0.625rem] text-fg-3">
          <template v-if="section.changed">+{{ section.added }} −{{ section.removed }}</template>
          <template v-else>unchanged</template>
        </span>
      </div>
      <div v-if="section.lines.length" class="py-0.5">
        <div v-for="(line, index) in section.lines" :key="`${section.id}-${index}`" class="ix-diff-line" :data-kind="line.type">
          <span class="ix-diff-mark" aria-hidden="true">{{ marker(line) }}</span>
          <span class="min-w-0">
            <template v-if="line.tokens">
              <span
                v-for="(token, tokenIndex) in line.tokens"
                :key="tokenIndex"
                :class="token.type === 'added' ? 'ix-diff-word-add' : token.type === 'removed' ? 'ix-diff-word-remove' : undefined"
              >{{ token.text }}</span>
            </template>
            <template v-else>{{ line.text }}</template>
          </span>
        </div>
      </div>
      <p v-else class="px-3 py-2 text-xs text-fg-3">This section no longer exists in the target version.</p>
    </section>
  </div>
</template>
