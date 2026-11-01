<script setup lang="ts">
import { computed } from "vue"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { CertificationTier } from "@/lib/certification"
import { tierLabel, tierMeaning } from "@/lib/certification"
import { formatUtc } from "@/lib/format"

const props = withDefaults(
  defineProps<{
    tier: CertificationTier
    recordId?: string | null
    component?: string | null
    certifiedAt?: string | null
    detail?: string | null
    size?: "sm" | "md"
    decorative?: boolean
  }>(),
  {
    recordId: null,
    component: null,
    certifiedAt: null,
    detail: null,
    size: "sm",
    decorative: false,
  },
)

const label = computed(() => tierLabel(props.tier))
const meaning = computed(() => tierMeaning(props.tier))
const aria = computed(() => {
  const parts = [`${label.value} tier.`, meaning.value]
  if (props.recordId) parts.push(`Record ${props.recordId}.`)
  if (props.certifiedAt) parts.push(`Certified ${formatUtc(props.certifiedAt)}.`)
  return parts.join(" ")
})
</script>

<template>
  <Tooltip v-if="!decorative">
    <TooltipTrigger as-child>
      <span
        class="ix-tier-mark"
        :data-tier="tier"
        :data-size="size"
        role="img"
        :aria-label="aria"
        tabindex="0"
      >
        <span class="ix-tier-mark-shape" aria-hidden="true" />
      </span>
    </TooltipTrigger>
    <TooltipContent
      side="top"
      align="start"
      :side-offset="6"
      class="!max-w-xs !items-start !rounded-lg !border !border-line !bg-overlay !px-3 !py-2.5 !text-fg-1 !shadow-[0_8px_24px_rgba(0,0,0,.4)]"
    >
      <span class="block">
        <span class="block text-xs font-semibold">{{ label }} tier</span>
        <span class="mt-1 block text-xs leading-4 text-fg-2">{{ meaning }}</span>
        <span v-if="detail" class="mt-1 block font-mono text-[0.8125rem] text-fg-3">{{ detail }}</span>
        <span v-if="recordId" class="mt-1 block font-mono text-[0.8125rem] text-fg-3">
          record {{ recordId }}
        </span>
        <span v-if="component" class="mt-0.5 block text-[0.8125rem] text-fg-3">
          certified by {{ component }}
        </span>
        <span v-if="certifiedAt" class="mt-0.5 block font-mono text-[0.8125rem] text-fg-3">
          {{ formatUtc(certifiedAt) }}
        </span>
      </span>
    </TooltipContent>
  </Tooltip>
  <span v-else class="ix-tier-mark" :data-tier="tier" :data-size="size" aria-hidden="true">
    <span class="ix-tier-mark-shape" />
  </span>
</template>

<style scoped>
.ix-tier-mark {
  display: inline-flex;
  width: 0.875rem;
  height: 0.875rem;
  flex: none;
  align-items: center;
  justify-content: center;
  border-radius: 1px;
  color: var(--ix-fg-2);
}

.ix-tier-mark[data-size="sm"] {
  width: 0.75rem;
  height: 0.75rem;
}

.ix-tier-mark:focus-visible {
  outline: 2px solid var(--ix-accent);
  outline-offset: 2px;
}

.ix-tier-mark-shape {
  display: block;
  width: 100%;
  height: 100%;
  border-radius: 1px;
}

.ix-tier-mark[data-tier="evidence"] .ix-tier-mark-shape {
  background: var(--ix-fg-1);
}

.ix-tier-mark[data-tier="metadata"] .ix-tier-mark-shape {
  border: 1px solid var(--ix-fg-1);
  background: linear-gradient(135deg, var(--ix-fg-1) 50%, transparent 50%);
}

.ix-tier-mark[data-tier="uncertified"] .ix-tier-mark-shape {
  border: 1.5px dashed var(--ix-fg-2);
}

.ix-tier-mark[data-tier="unavailable"] .ix-tier-mark-shape {
  border: 1px solid var(--ix-line);
  background-image: repeating-linear-gradient(
    45deg,
    transparent 0 2px,
    color-mix(in srgb, var(--ix-line-strong) 65%, transparent) 2px 3px
  );
}

.ix-tier-mark[data-tier="preview"] .ix-tier-mark-shape {
  border: 1px solid var(--ix-line);
  background-image: repeating-linear-gradient(
    135deg,
    var(--ix-accent) 0 2px,
    transparent 2px 4px
  );
}
</style>
