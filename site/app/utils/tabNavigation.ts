// Roving-tabindex arrow navigation for tab lists: ArrowLeft/ArrowRight wrap,
// Home jumps to the first tab, End to the last.
export function nextTabIndex(key: string, index: number, count: number): number {
  if (key === 'ArrowLeft') return (index - 1 + count) % count
  if (key === 'ArrowRight') return (index + 1) % count
  if (key === 'Home') return 0
  return count - 1
}
