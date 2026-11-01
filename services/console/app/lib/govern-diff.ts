import { diffWords, type TextDiffToken } from "./text-diff"

export type DiffableSection = {
  id: string
  label: string
  lines: string[]
}

export type DiffOpType = "same" | "removed" | "added"

export type DiffWordToken = TextDiffToken

export type DiffOp = {
  type: DiffOpType
  text: string
  /** Word-level tokens exist only for paired removed/added lines. */
  tokens?: DiffWordToken[]
}

export type SectionDiff = {
  id: string
  label: string
  changed: boolean
  added: number
  removed: number
  lines: DiffOp[]
}

export type DiffSummary = {
  sectionsChanged: number
  sectionsTotal: number
  added: number
  removed: number
}

export type SplitDiffRow = {
  left: DiffOp | null
  right: DiffOp | null
}

function lcsTable(left: string[], right: string[]): number[][] {
  const table: number[][] = Array.from({ length: left.length + 1 }, () => new Array<number>(right.length + 1).fill(0))
  for (let row = left.length - 1; row >= 0; row -= 1) {
    for (let col = right.length - 1; col >= 0; col -= 1) {
      table[row]![col] = left[row] === right[col]
        ? table[row + 1]![col + 1]! + 1
        : Math.max(table[row + 1]![col]!, table[row]![col + 1]!)
    }
  }
  return table
}

export function diffLines(previous: string[], next: string[]): DiffOp[] {
  const table = lcsTable(previous, next)
  const ops: DiffOp[] = []
  let row = 0
  let col = 0

  while (row < previous.length && col < next.length) {
    if (previous[row] === next[col]) {
      ops.push({ type: "same", text: previous[row]! })
      row += 1
      col += 1
    } else if (table[row + 1]![col]! >= table[row]![col + 1]!) {
      ops.push({ type: "removed", text: previous[row]! })
      row += 1
    } else {
      ops.push({ type: "added", text: next[col]! })
      col += 1
    }
  }
  while (row < previous.length) {
    ops.push({ type: "removed", text: previous[row]! })
    row += 1
  }
  while (col < next.length) {
    ops.push({ type: "added", text: next[col]! })
    col += 1
  }
  return ops
}

/** Pairs adjacent removed/added lines and attaches word-level tokens to both sides. */
function annotateWordDiff(lines: DiffOp[]): DiffOp[] {
  for (let index = 0; index < lines.length - 1; index += 1) {
    const current = lines[index]!
    const next = lines[index + 1]!
    if (current.type !== "removed" || next.type !== "added") continue
    const tokens = diffWords(current.text, next.text)
    current.tokens = tokens.filter((token) => token.type !== "added")
    next.tokens = tokens.filter((token) => token.type !== "removed")
  }
  return lines
}

export function diffDirectiveSections(previous: DiffableSection[], next: DiffableSection[]): SectionDiff[] {
  const previousById = new Map(previous.map((section) => [section.id, section]))
  const nextIds = new Set(next.map((section) => section.id))
  const result: SectionDiff[] = []

  for (const section of next) {
    const before = previousById.get(section.id)
    const lines = annotateWordDiff(diffLines(before?.lines ?? [], section.lines))
    const added = lines.filter((line) => line.type === "added").length
    const removed = lines.filter((line) => line.type === "removed").length
    result.push({
      id: section.id,
      label: section.label,
      changed: added > 0 || removed > 0 || !before,
      added,
      removed,
      lines,
    })
  }

  for (const section of previous) {
    if (nextIds.has(section.id)) continue
    result.push({
      id: section.id,
      label: section.label,
      changed: section.lines.length > 0,
      added: 0,
      removed: section.lines.length,
      lines: section.lines.map((line) => ({ type: "removed", text: line })),
    })
  }

  return result
}

export function diffSummary(sections: SectionDiff[]): DiffSummary {
  return sections.reduce<DiffSummary>(
    (summary, section) => ({
      sectionsChanged: summary.sectionsChanged + (section.changed ? 1 : 0),
      sectionsTotal: summary.sectionsTotal + 1,
      added: summary.added + section.added,
      removed: summary.removed + section.removed,
    }),
    { sectionsChanged: 0, sectionsTotal: 0, added: 0, removed: 0 },
  )
}

export function splitDiffRows(lines: DiffOp[]): SplitDiffRow[] {
  const rows: SplitDiffRow[] = []
  for (let index = 0; index < lines.length; index += 1) {
    const current = lines[index]!
    if (current.type === "same") {
      rows.push({ left: current, right: current })
      continue
    }
    if (current.type === "removed") {
      const next = lines[index + 1]
      if (next?.type === "added") {
        rows.push({ left: current, right: next })
        index += 1
      } else {
        rows.push({ left: current, right: null })
      }
      continue
    }
    rows.push({ left: null, right: current })
  }
  return rows
}
