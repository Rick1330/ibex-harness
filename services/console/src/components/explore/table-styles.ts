/** Vercel Deployments–inspired list density: compact, hairline rows. */
export const listTable = {
  shell: "w-full",
  frame:
    "w-full overflow-hidden rounded-lg border border-border bg-card shadow-[0_1px_2px_oklch(0_0_0/0.06)] dark:shadow-none",
  table: "w-full border-collapse text-[13px]",
  headRow: "border-b border-border/80 bg-muted/40",
  head: "h-8 px-3 text-left text-[11px] font-medium tracking-wide text-muted-foreground whitespace-nowrap",
  row: "group border-b border-border/60 transition-colors hover:bg-muted/40 data-[state=selected]:bg-muted/50",
  cell: "px-3 py-2.5 align-middle text-[13px] leading-snug",
  primary: "text-[13px] font-medium text-foreground",
  mono: "font-mono text-[12px] leading-snug",
  meta: "text-[12px] text-muted-foreground",
  muted: "text-[12px] text-muted-foreground",
} as const

/** @deprecated Prefer listTable — kept as alias so existing imports keep working. */
export const exploreTable = {
  head: listTable.head,
  cell: listTable.cell,
  mono: listTable.mono,
  meta: `${listTable.mono} ${listTable.meta}`,
} as const
