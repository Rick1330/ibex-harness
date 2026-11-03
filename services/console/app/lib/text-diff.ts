export type TextDiffToken = { type: "same" | "removed" | "added"; text: string }

function tokenize(value: string): string[] {
  return value.split(/(\s+)/).filter((token) => token.length > 0)
}

/**
 * Minimal LCS word diff, adequate for short memory statements. Returns tokens
 * suitable for inline struck-through removed / highlighted added rendering.
 */
export function diffWords(previous: string, next: string): TextDiffToken[] {
  const left = tokenize(previous)
  const right = tokenize(next)
  const rows = left.length
  const cols = right.length

  const table: number[][] = Array.from({ length: rows + 1 }, () => new Array<number>(cols + 1).fill(0))
  for (let row = rows - 1; row >= 0; row -= 1) {
    for (let col = cols - 1; col >= 0; col -= 1) {
      table[row]![col] = left[row] === right[col] ? table[row + 1]![col + 1]! + 1 : Math.max(table[row + 1]![col]!, table[row]![col + 1]!)
    }
  }

  const tokens: TextDiffToken[] = []
  const push = (type: TextDiffToken["type"], text: string): void => {
    const last = tokens.at(-1)
    if (last && last.type === type) last.text += text
    else tokens.push({ type, text })
  }

  let row = 0
  let col = 0
  while (row < rows && col < cols) {
    if (left[row] === right[col]) {
      push("same", left[row]!)
      row += 1
      col += 1
    } else if (table[row + 1]![col]! >= table[row]![col + 1]!) {
      push("removed", left[row]!)
      row += 1
    } else {
      push("added", right[col]!)
      col += 1
    }
  }
  while (row < rows) {
    push("removed", left[row]!)
    row += 1
  }
  while (col < cols) {
    push("added", right[col]!)
    col += 1
  }
  return tokens
}
