<script setup lang="ts">
import { computed } from "vue"
import { Check, ChevronDown } from "@lucide/vue"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

const props = withDefaults(
  defineProps<{
    label: string
    options: { value: string; label?: string; count?: number }[]
    modelValue: string[]
  }>(),
  {},
)

const emit = defineEmits<{ "update:modelValue": [value: string[]] }>()

const active = computed(() => props.modelValue.length)

function toggle(value: string, checked: boolean): void {
  const next = checked ? [...new Set([...props.modelValue, value])] : props.modelValue.filter((entry) => entry !== value)
  emit("update:modelValue", next)
}
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <button
        type="button"
        class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        :class="
          active
            ? 'border-accent-memory/40 bg-memory-tint text-fg-1'
            : 'border-line-subtle bg-surface-1 text-fg-2 hover:border-line hover:text-fg-1'
        "
        :aria-label="active ? `${label} filter, ${active} selected` : `${label} filter`"
      >
        {{ label }}
        <span v-if="active" class="rounded-full bg-surface-1 px-1.5 py-0.5 font-mono text-[0.625rem] leading-none tabular-nums">{{ active }}</span>
        <ChevronDown :size="11" :stroke-width="1.9" class="text-fg-3" aria-hidden="true" />
      </button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" class="w-56 p-1.5">
      <DropdownMenuLabel class="px-2 py-1.5 text-xs font-semibold text-fg-1">{{ label }}</DropdownMenuLabel>
      <DropdownMenuSeparator />
      <DropdownMenuCheckboxItem
        v-for="option in options"
        :key="option.value"
        :model-value="modelValue.includes(option.value)"
        class="gap-2 py-1.5 text-xs"
        @update:model-value="toggle(option.value, Boolean($event))"
        @select.prevent
      >
        <span class="min-w-0 flex-1 truncate">{{ option.label ?? option.value }}</span>
        <span v-if="option.count !== undefined" class="font-mono text-[0.625rem] text-fg-3 tabular-nums">{{ option.count }}</span>
        <Check v-if="modelValue.includes(option.value)" :size="12" :stroke-width="2.2" class="text-accent-memory" aria-hidden="true" />
      </DropdownMenuCheckboxItem>
      <template v-if="active">
        <DropdownMenuSeparator />
        <DropdownMenuItem class="gap-2 py-1.5 text-xs" @select="emit('update:modelValue', [])">
          Clear {{ label.toLowerCase() }}
        </DropdownMenuItem>
      </template>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
