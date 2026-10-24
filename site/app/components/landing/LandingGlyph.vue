<script setup lang="ts">
const glyphs = {
  'arrow-right': ['M3 12h15', 'M11 5l7 7-7 7', 'M21 4v16'],
  'arrow-down': ['M12 3v15', 'M5 11l7 7 7-7', 'M4 21h16'],
  'arrow-up-right': ['M6 18L18 6', 'M8 6h10v10'],
  'check': ['M4 8V4h4', 'M20 16v4h-4', 'M7 12l4 4 7-8'],
  'copy': ['M8 8h11v11H8z', 'M5 16V5h11'],
  'terminal': ['M3 5h18v14H3z', 'M7 10l3 2-3 2', 'M12 15h5'],
  'request': ['M3 8h14', 'M14 5l3 3-3 3', 'M21 16H7', 'M10 13l-3 3 3 3'],
  'context': ['M4 5h16', 'M4 12h10', 'M4 19h16', 'M17 9v6'],
  'trace': ['M3 18h4V9h5v6h4V5h5'],
  'database': ['M4 5h16v5H4z', 'M4 14h16v5H4z', 'M7 7.5h.01', 'M7 16.5h.01'],
  'key': ['M4 10h6v6H4z', 'M10 13h9', 'M16 13v3', 'M19 13v2'],
  'shield': ['M12 3l8 3v6c0 5-4 8-8 9-4-1-8-4-8-9V6z', 'M8 12l3 3 5-6'],
  'gauge': ['M4 17a8 8 0 1 1 16 0', 'M12 17l4-5'],
  'radio': ['M12 11h.01', 'M8.5 14.5a5 5 0 1 1 7 0', 'M5.5 17.5a9 9 0 1 1 13 0'],
  'file-clock': ['M6 3h8l4 4v5', 'M6 3v18h6', 'M14 3v5h5', 'M17 14v4l3 2'],
  'file-json': ['M6 3h8l4 4v14H6z', 'M14 3v5h5', 'M9 13h1v5H9', 'M14 13h1v2h-1z', 'M18 13h1v5h-1'],
  'lock': ['M5 11h14v9H5z', 'M8 11V7a4 4 0 0 1 8 0v4'],
  'fingerprint': ['M4 8h16', 'M4 16h16', 'M8 4v16', 'M16 4v16'],
  'circle-check': ['M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z', 'M8 12l3 3 5-6'],
} as const
type GlyphName = keyof typeof glyphs
defineProps<{ name: GlyphName }>()
</script>

<template>
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="square"
    stroke-linejoin="miter"
    aria-hidden="true"
  >
    <path v-for="d in glyphs[name]" :key="d" :d="d" />
  </svg>
</template>
