import { existsSync, realpathSync } from 'node:fs'
import { readFile, readdir } from 'node:fs/promises'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const site = resolve(here, '..')
const allowlistPath = join(here, 'claim-numbers.allowlist.json')
const allowlistName = 'scripts/claim-numbers.allowlist.json'

/**
 * Where the scan reads, relative to a site root, and what each root is for.
 *
 * - `prose`: rendered prose — every page, docs page, and blog post, and every
 *   component whose template and `<script>` strings render inside them. A claim
 *   hard-coded in a component reaches the reader exactly as one written in
 *   markdown does, so it is scanned by the same rule set.
 * - `data`: typed data — the claim-bearing strings a page renders and the numbers
 *   it plots. A number a reader could take as a result is authored here or
 *   imported from a committed artifact, so this is the surface the numeric-claim
 *   rule gates. Page templates and components hold artifact values and static
 *   axis/label strings, not new results; widening the numeric rule past this root
 *   would require an allowlist entry for every documented target and every `pNN`
 *   field name in the docs tree.
 * - `ledger`: the one file in `data` whose claims are read from object fields and
 *   labelled tuples rather than from whole lines.
 * - `benchmarks`: published benchmark artifacts. `validate_published_data.py`
 *   owns their schema, so this checker reads only the string values a reader sees
 *   — a `note`, a `recall` definition, a gate check name — and applies the prose
 *   rules to them. The numbers in these files are the schema's business, not a
 *   sentence's, so the numeric rule stays out of this root.
 *
 * Declaring the layout once lets `scan` take any site root: the real tree and a
 * test fixture holding the same layout are walked and dispatched by the same code,
 * so a test exercises the roots this check actually reads.
 */
const layout = {
  prose: ['app/pages', 'content/docs', 'content/blog', 'app/components'],
  data: 'app/data',
  ledger: 'app/data/ledger.ts',
  benchmarks: 'public/benchmarks',
}

/**
 * ADRs and archived roadmaps are records of a past decision, not live claims.
 */
const skippedDirectories = new Set(['adr', 'roadmap-archive'])

const denials = /\b(?:not|never|no|nor|none|isn't|aren't|without|avoid|rather than|beyond|cannot|can't|does not|do not|remains? open|gap)\b/i
const prohibited = [
  { pattern: /production[- ]ready/gi, label: 'positive production-readiness claim' },
  { pattern: /battle[- ]tested/gi, label: 'unsupported battle-tested claim' },
  { pattern: /enterprise[- ]grade/gi, label: 'unsupported enterprise-grade claim' },
  { pattern: /five nines|99\.9+\s*%/gi, label: 'unsupported availability number' },
  { pattern: /guaranteed\s+(?:uptime|latency|availability|isolation)/gi, label: 'guarantee claim' },
]

/**
 * A denial only excuses a claim in its own clause. A comma ends a clause too, so
 * "not audited, enterprise-grade software" must not pass: the denial covers
 * "audited", not the claim after the comma. Contrast "not production-ready, but
 * battle-tested", where the `but` already breaks the clause.
 *
 * A full stop ends a sentence unless a digit follows it directly: that is a
 * decimal fraction or a version component (`0.97`, `v1.9`, `.97`), so the metric
 * word that qualifies the score stays inside its own clause. Any other full stop
 * ends the sentence, including one that trails a version or a unit: in "Not
 * measured in v1. Production-ready." the denial belongs to the first sentence and
 * must not excuse the claim in the second. Reading a stop as part of the number
 * only when digits sit on both sides was wrong the other way: it read the stop in
 * `v1.` as mid-clause and let a denial cross the sentence.
 */
const clauseBreaks = /\.(?!\d)|[;,!?:]|\b(?:but|however|yet|although|though|while)\b/gi

/**
 * A number that reads as a measurement: a digit with a unit suffix, or a
 * percentile token. Field names such as `latency_ms_p95` and bare versions such
 * as `v1` are not claims.
 */
const numericClaim = /(?<![A-Za-z0-9_.])(?:\d[\d,.]*\s*(?:%|ms|µs|ns)(?!\w)|p\d{2,3}(?!\w))/g

/**
 * A number that reads as a result without carrying a unit: a bare score such as
 * `0.99` or `.97`. It is a claim only when its own clause names the metric it
 * measures. The lookbehind keeps `routing_0.5` a field name and `(?!\d)` stops a
 * decimal short of a longer number. A number that carries a unit is the claim the
 * rule above already reports, so it is excluded here by the predicate below
 * rather than by the pattern: `99.9%` and `1.5 ms` need a percentage and a time
 * unit excluded, and with all of them in the pattern the expression crossed the
 * complexity limit that keeps it reviewable. It was also wrong there: `\b` after
 * `%` matched only when another word followed, so a percentage at the end of a
 * clause was read as a unitless score too, and one measurement produced two
 * findings whose allowlist entry for the percentage still left a failure behind.
 * It is gated by the same `app/data` scope as those claims, where a reader-facing
 * result is authored.
 */
const dimensionlessScore = /(?<![A-Za-z0-9_.])(?:\d+\.\d+|\.\d+)(?!\d)/g
const scoreMetrics = /\b(?:mrr|precision|recall|ndcg|accuracy|f1|scores?|p50|p95|p99)\b/i

/**
 * What may follow a score and show it is not dimensionless: the next component of
 * a version, read directly after the number, or a unit the measurement rule above
 * already reports — a percentage or a time unit — read after optional
 * whitespace. `v1.0.9` and `1.0.9` therefore yield `1.0` from the pattern and are
 * dropped here on the `.9` that follows.
 */
const versionTail = /^\.\d/
const unitSuffix = /^(?:%|(?:ms|µs|ns)\b)/

function carriesAUnit(text, index, length) {
  const rest = text.slice(index + length)
  return versionTail.test(rest) || unitSuffix.test(rest.trimStart())
}

/**
 * The artifact a quoted number must name on its own line: the benchmarks page,
 * a benchmark JSON file, a CI run, or a gold set.
 */
const artifactReference = /(?:\/benchmarks|benchmark-data|run\s+\d+|gold set)/i

const numericLabel = 'numeric claim without an artifact reference'
const scoreLabel = 'dimensionless score without an artifact reference'
const allowlistableLabels = new Set([numericLabel, scoreLabel])
export const unreadableLabel = 'claim value that cannot be inspected (needs a static string literal)'

const proseFile = name => /\.(?:md|vue)$/.test(name)
const dataFile = name => name.endsWith('.ts') && !name.endsWith('.test.ts')
const benchmarkFile = name => name.endsWith('.json')
const isText = value => typeof value === 'string'
const isFilledText = value => isText(value) && value.length > 0

/**
 * Every file under `dir` that `accept` claims. The entries are walked
 * concurrently and `Promise.all` preserves their order, so the result is the
 * same list a depth-first walk produced, deterministically.
 */
async function walk(dir, accept) {
  const entries = await readdir(dir, { withFileTypes: true })
  const found = await Promise.all(entries.map(async (entry) => {
    const full = join(dir, entry.name)
    if (!entry.isDirectory()) return accept(entry.name) ? [full] : []
    if (skippedDirectories.has(entry.name)) return []
    return walk(full, accept)
  }))
  return found.flat()
}

/**
 * The clause boundaries of one text, found once and reused by every occurrence in
 * it: `starts[i]` and `ends[i]` are the offsets the i-th break starts and ends at.
 * Both lists increase, so an occurrence's clause is read by binary search instead of
 * by rescanning the text for every match, which is quadratic on a text with many
 * clauses and many occurrences.
 */
function clauseIndex(text) {
  const breaks = [...text.matchAll(clauseBreaks)]
  return {
    text,
    starts: breaks.map(match => match.index),
    ends: breaks.map(match => match.index + match[0].length),
  }
}

/**
 * The index of the first entry of the increasing list `sorted` that is at least
 * `value`, or -1 when no entry is.
 */
function firstAtLeast(sorted, value) {
  let low = 0
  let high = sorted.length
  while (low < high) {
    const middle = (low + high) >> 1
    if (sorted[middle] < value) low = middle + 1
    else high = middle
  }
  return low < sorted.length ? low : -1
}

/**
 * The index of the last entry of the increasing list `sorted` that is at most
 * `value`, or -1 when no entry is: the entry before the first one that is greater
 * than `value`.
 */
function lastAtMost(sorted, value) {
  const after = firstAtLeast(sorted, value + 1)
  return after === -1 ? sorted.length - 1 : after - 1
}

/**
 * The clause that contains `index`, as half-open offsets into `clauses.text`. The
 * clause starts after the last break that ends at or before the match and ends at
 * the first break that starts at or after it, so both a denial and a metric word are
 * scoped to the claim they surround.
 */
function clauseBounds(clauses, index) {
  const start = clauses.ends[lastAtMost(clauses.ends, index)]
  const next = clauses.starts[firstAtLeast(clauses.starts, index)]
  return { start: start ?? 0, end: next ?? clauses.text.length }
}

const clauseBefore = (clauses, index) => clauses.text.slice(clauseBounds(clauses, index).start, index)

function clauseAround(clauses, index, length) {
  const { start, end } = clauseBounds(clauses, index)
  return clauses.text.slice(start, Math.max(end, index + length))
}

/**
 * Every occurrence of every prohibited pattern is evaluated on its own, as its
 * label and the half-open span it occupies. A denial excuses only the occurrence in
 * its clause: "Not production-ready; production-ready" has one denied and one
 * undenied occurrence. The clause boundaries are read once for the whole text.
 */
function phraseMatches(text) {
  const clauses = clauseIndex(text)
  return prohibited.flatMap(rule => [...text.matchAll(rule.pattern)]
    .filter(match => !denials.test(clauseBefore(clauses, match.index)))
    .map(match => ({ label: rule.label, start: match.index, end: match.index + match[0].length })))
}

/**
 * Every prohibited phrase one text states, with repeated labels collapsed to one
 * finding per scanned text.
 */
export function phraseViolations(text) {
  return [...new Set(phraseMatches(text).map(match => match.label))]
}

const tokenClaims = (pattern, text, label, accept) => [...text.matchAll(pattern)]
  .filter(match => accept(match))
  .map(match => ({ label, token: match[0] }))

/**
 * A unitless score is a claim only when its own clause names the metric. A number
 * that carries a unit is not one: the measurement rule already reports it, so it
 * is dropped here rather than counted twice.
 */
function isScoreClaim(clauses, match) {
  const length = match[0].length
  if (carriesAUnit(clauses.text, match.index, length)) return false
  return scoreMetrics.test(clauseAround(clauses, match.index, length))
}

/**
 * Numeric claims, one finding per occurrence so the allowlist excuses one number
 * rather than the line it sits on. A line that names its artifact supports all
 * of its numbers and reports nothing.
 */
function numericViolations(text) {
  if (artifactReference.test(text)) return []
  const clauses = clauseIndex(text)
  const measures = tokenClaims(numericClaim, text, numericLabel, () => true)
  const scores = tokenClaims(dimensionlessScore, text, scoreLabel, match => isScoreClaim(clauses, match))
  return [...measures, ...scores]
}

/**
 * `ledger.ts` is code as well as claims: only the `name` and `detail` string
 * values are claims, so an object key or a derived count cannot trip a rule.
 * A claim field is read from a single-quoted, double-quoted, or template literal,
 * on one line or several, that is the whole value the field renders.
 */
const claimKey = /^[ \t]*(name|detail)\??[ \t]*:[ \t]*(?:\r?\n[ \t]*)?/gm

/**
 * The only non-literal value shape accepted after a claim field is a primitive
 * type annotation (`detail: string`) inside an interface: it declares the field
 * rather than carrying a claim. Every other non-literal value is reported, so a
 * claim the checker cannot read is a failure and never a silent skip.
 */
const primitiveAnnotation = /^(?:string|number|boolean|unknown)(?:\[\])?$/

/**
 * The separators that follow a value and belong to the object syntax rather than
 * to the value: a comma or any whitespace character. Each is tested on its own so
 * the strip below stays linear; an unanchored `[,\s]+$` pattern backtracks
 * polynomially on a long line that does not end in a separator.
 */
const valueSeparator = /[,\s]/

/**
 * The rest of the line after `start`, with the separators that trail the value
 * removed. The scan runs backwards from the end and stops at the first character
 * that is part of the value.
 */
function expressionOnLine(source, start) {
  const line = source.slice(start).split('\n')[0] ?? ''
  let end = line.length
  while (end > 0 && valueSeparator.test(line[end - 1])) end -= 1
  return line.slice(0, end)
}

/**
 * The single-character escapes a claim literal may carry and the character each
 * contributes. They are decoded rather than dropped so the claim text is the text
 * the page renders.
 */
const singleCharEscapes = new Map([
  ['n', '\n'],
  ['t', '\t'],
  ['r', '\r'],
  ['0', '\0'],
  ['b', '\b'],
  ['f', '\f'],
  ['v', '\v'],
  ['\\', '\\'],
  ["'", "'"],
  ['"', '"'],
  ['`', '`'],
])

const hexDigit = /[0-9a-f]/i

/**
 * Whether `char` is a hexadecimal digit. A character past the end of the source is
 * not one, so a truncated escape fails to decode.
 */
const isHexDigit = char => char !== undefined && hexDigit.test(char)

/**
 * Whether `code` is a code point a JavaScript literal can hold. A value outside
 * Unicode is not text any page renders.
 */
const isCodePoint = code => code >= 0 && code <= 0x10ffff

/**
 * A decoded escape, or `null` when its code point is outside Unicode.
 */
const decodedCodePoint = (code, next) => (isCodePoint(code) ? { value: String.fromCodePoint(code), next } : null)

/**
 * The value a fixed-width hexadecimal escape (`\xNN`, `\uNNNN`) contributes and
 * the index the scan resumes at, after the run of hex digits. `null` when the run
 * is short or a digit is not hex.
 */
function readFixedHexEscape(source, index, width) {
  const digits = source.slice(index, index + width)
  if (digits.length !== width || ![...digits].every(isHexDigit)) return null
  return decodedCodePoint(Number.parseInt(digits, 16), index + width)
}

/**
 * The value a braced code-point escape (`\u{...}`) contributes and the index the
 * scan resumes at, after the closing brace: one to six hex digits between braces.
 * `null` when a brace is missing or a digit is not hex.
 */
function readBracedHexEscape(source, index) {
  const close = source.indexOf('}', index)
  const digits = source.slice(index, close)
  if (close === -1 || digits.length < 1 || digits.length > 6) return null
  if (![...digits].every(isHexDigit)) return null
  return decodedCodePoint(Number.parseInt(digits, 16), close + 1)
}

const readUnicodeEscape = (source, index) => (source[index] === '{'
  ? readBracedHexEscape(source, index + 1)
  : readFixedHexEscape(source, index, 4))

/**
 * The only characters a claim literal may open with. Without this test the first
 * character of any expression would be read as an opening quote: `messages.claim`
 * would close on the `m` of `claim` and hand back `essages.clai`, accepting a
 * dynamic value as if it were a static claim.
 */
const literalQuotes = new Set(["'", '"', '`'])

const opensLiteral = quote => literalQuotes.has(quote)

/**
 * A template literal is the only one that may span lines and carry an
 * interpolation.
 */
const isTemplateLiteral = quote => quote === '`'

/**
 * Whether the text at `index` opens a template interpolation. Its runtime text is
 * not in the source, so the value cannot be read from it.
 */
const isInterpolation = (source, index) => source[index] === '$' && source[index + 1] === '{'

/**
 * The value an escape sequence contributes and the index the scan resumes at,
 * after the whole sequence. `\xNN`, `\uNNNN`, `\u{...}` and the standard
 * single-character escapes are decoded, because the claim text has to be the text
 * the page renders: passing `\x35 ms` through as `x35 ms` hides the numeric claim
 * behind the escape. `null` means the sequence is not one this checker can decode,
 * and the value that holds it is uninspectable rather than read wrong.
 */
function readEscape(source, index) {
  const char = source[index + 1]
  if (singleCharEscapes.has(char)) return { value: singleCharEscapes.get(char), next: index + 2 }
  if (char === 'x') return readFixedHexEscape(source, index + 2, 2)
  if (char === 'u') return readUnicodeEscape(source, index + 2)
  return null
}

/**
 * Whether `char` opens an escape sequence. The caller reads it with `readEscape`
 * and continues after the whole sequence, whose length depends on the escape.
 */
const opensEscape = char => char === '\\'

/**
 * Whether `char` closes the literal that opened with `quote`.
 */
const closesLiteral = (char, quote) => char === quote

/**
 * Whether the character at `index` ends the scan without a readable value: a
 * single-quoted literal that breaks across lines, or a template that
 * interpolates. A template may hold newlines, so the line break is unreadable
 * only outside one.
 */
function unreadableAt(source, index, template) {
  return template ? isInterpolation(source, index) : source[index] === '\n'
}

/**
 * Reads the literal that starts at `start`. `null` means the value is not a
 * static string: it does not open with a quote or backtick, it is unterminated, a
 * single-line literal that breaks across lines, or a template with `${}`
 * interpolation, whose runtime text is not in the source. The scan decides per
 * character whether the literal closes, escapes, or is unreadable, and otherwise
 * takes the character as part of the value.
 */
function readLiteral(source, start) {
  const quote = source[start]
  if (!opensLiteral(quote)) return null
  const template = isTemplateLiteral(quote)
  let value = ''
  let index = start + 1
  while (index < source.length) {
    const char = source[index]
    if (closesLiteral(char, quote)) return { value, end: index + 1 }
    if (opensEscape(char)) {
      const escape = readEscape(source, index)
      if (escape === null) return null
      value += escape.value
      index = escape.next
      continue
    }
    if (unreadableAt(source, index, template)) return null
    value += char
    index += 1
  }
  return null
}

/**
 * The characters that may follow a claim literal without making it one operand of
 * a larger expression: the object syntax that closes the value and the separator
 * before the next property. Whitespace, newlines included, is skipped first. Any
 * other character — `+`, a call, another literal — means the rendered text is
 * built at runtime, so the literal alone is not the claim.
 */
const valueTerminator = /[;,}\])]/

function endsValue(source, index) {
  const next = source.slice(index).trimStart()[0]
  return next === undefined || valueTerminator.test(next)
}

/**
 * The offset each line of `source` starts at, indexed once. Resolving a line used to
 * rescan the source from its start, which is quadratic on a file the scan reads many
 * positions from.
 */
function lineStarts(source) {
  const starts = [0]
  for (let at = source.indexOf('\n'); at !== -1; at = source.indexOf('\n', at + 1)) starts.push(at + 1)
  return starts
}

/**
 * The 1-based line `offset` falls on, by binary search over the increasing `starts`.
 */
function lineAt(starts, offset) {
  let low = 0
  let high = starts.length
  while (low < high) {
    const middle = (low + high) >> 1
    if (starts[middle] <= offset) low = middle + 1
    else high = middle
  }
  return low
}

/**
 * The compact row arrays of `ledger.ts`, matched by the annotation that makes them
 * readable: `const <name>: readonly <RowType>[] = [`. The table states each field
 * name once, in the labelled tuple `<RowType>`, and holds the values positionally,
 * so a value's field is the position it sits at. Discovery is by the annotation
 * rather than by a list of array names, so a row array added later is scanned
 * without editing this script.
 */
const rowArrayDeclaration = /const\s+\w+\s*:\s*readonly\s+(\w+)\[\]\s*=\s*\[/g

/**
 * The fields of a row that carry a claim, in the order the object form rendered
 * them. A row array whose tuple labels neither field carries no claim and is
 * skipped, exactly as a non-claim key is skipped today.
 */
const claimFields = ['name', 'detail']

/**
 * `text` with the characters a regular expression would read as syntax escaped, so
 * an identifier taken from the source can be matched literally.
 */
const escapeRegExp = text => text.replace(/[.*+?^${}()|[\]\\]/g, String.raw`\$&`)

/**
 * The text between the bracket that opens at `index` and the one that closes it, or
 * `null` when it never closes. Quoted text is skipped whole, so a bracket inside a
 * string cannot move the depth.
 */
function readBracketed(source, index) {
  let depth = 0
  let cursor = index
  while (cursor < source.length) {
    const literal = literalQuotes.has(source[cursor]) ? readLiteral(source, cursor) : null
    if (literal !== null) {
      cursor = literal.end
      continue
    }
    if (source[cursor] === '[') depth += 1
    if (source[cursor] === ']') {
      depth -= 1
      if (depth === 0) return source.slice(index + 1, cursor)
    }
    cursor += 1
  }
  return null
}

/**
 * The label of every element in the labelled tuple type `typeName`, or `null` when
 * the source does not declare that type as a readonly tuple of labelled elements.
 * The element list is read to its matching bracket rather than to the first `]`,
 * because an element type may index another type (`Gap['priority']`) and end a flat
 * match early: the truncated list would then hide the claim fields it lost and let
 * a row array be skipped instead of reported.
 */
function tupleLabels(source, typeName) {
  const declaration = new RegExp(String.raw`type\s+${escapeRegExp(typeName)}\s*=\s*readonly\s*\[`).exec(source)
  if (declaration === null) return null
  const elements = readBracketed(source, declaration.index + declaration[0].length - 1)
  if (elements === null) return null
  const labels = elements.split(',').map(element => element.split(':')[0].trim())
  return labels.every(label => /^[A-Za-z_$][\w$]*$/.test(label)) ? labels : null
}

/**
 * The index of every claim field in the labelled tuple `typeName`. `null` means the
 * tuple cannot be read, so the rows cannot be; `[]` means the tuple labels no claim
 * field.
 */
function claimFieldIndices(source, typeName) {
  const labels = tupleLabels(source, typeName)
  if (labels === null) return null
  return claimFields.map(field => labels.indexOf(field)).filter(index => index !== -1)
}

/**
 * Whether `char` is whitespace a row may be formatted across.
 */
const isWhitespace = char => char === ' ' || char === '\t' || char === '\n' || char === '\r'

/**
 * The index of the first character from `index` that is neither whitespace nor part
 * of a comment. A row array is scanned through its own trivia, so a comment between
 * two rows, or inside one, is not read as a value.
 */
function skipTrivia(source, index) {
  let cursor = index
  while (cursor < source.length) {
    if (isWhitespace(source[cursor])) {
      cursor += 1
      continue
    }
    if (source.startsWith('//', cursor)) {
      const end = source.indexOf('\n', cursor)
      cursor = end === -1 ? source.length : end + 1
      continue
    }
    if (source.startsWith('/*', cursor)) {
      const end = source.indexOf('*/', cursor + 2)
      cursor = end === -1 ? source.length : end + 2
      continue
    }
    return cursor
  }
  return cursor
}

/**
 * The static values of the row that opens at `index`, or `null` when an element is
 * not a literal this checker can read. Every element must be a literal: a row that
 * builds a value at runtime is uninspectable, not a row to skip.
 */
function readRow(source, index) {
  const values = []
  let cursor = skipTrivia(source, index + 1)
  while (cursor < source.length && source[cursor] !== ']') {
    const literal = readLiteral(source, cursor)
    if (literal === null) return null
    values.push(literal.value)
    cursor = skipTrivia(source, literal.end)
    if (source[cursor] === ',') cursor = skipTrivia(source, cursor + 1)
    else if (source[cursor] !== ']') return null
  }
  return source[cursor] === ']' ? { values, end: cursor + 1 } : null
}

/**
 * The claim values of every row from `start`, one entry per claim field at the line
 * its row starts on. A row that is not a literal list, or that is too short for the
 * fields its type labels, stops the scan and is reported: once a row is misread the
 * rest of the array cannot be trusted either.
 */
function scanRows(source, start, indices, starts) {
  const texts = []
  let cursor = start
  while (cursor < source.length) {
    cursor = skipTrivia(source, cursor)
    if (cursor >= source.length || source[cursor] === ']') return { texts, unreadable: [] }
    const line = lineAt(starts, cursor)
    const row = source[cursor] === '[' ? readRow(source, cursor) : null
    if (row === null || indices.some(index => index >= row.values.length)) {
      return { texts, unreadable: [{ line, text: expressionOnLine(source, cursor) }] }
    }
    for (const index of indices) texts.push({ line, text: row.values[index] })
    cursor = row.end
    if (source[cursor] === ',') cursor += 1
  }
  return { texts, unreadable: [] }
}

/**
 * The claim values of every compact row array in `ledger.ts`. A row array whose
 * tuple labels cannot be read is returned in `unreadable` and fails the check, so a
 * rename or a reformat that hides a claim is reported rather than skipped.
 */
function rowClaimTexts(source) {
  const texts = []
  const unreadable = []
  const starts = lineStarts(source)
  for (const declaration of source.matchAll(rowArrayDeclaration)) {
    const indices = claimFieldIndices(source, declaration[1])
    if (indices === null) {
      unreadable.push({ line: lineAt(starts, declaration.index), text: declaration[0] })
      continue
    }
    if (indices.length === 0) continue
    const rows = scanRows(source, declaration.index + declaration[0].length, indices, starts)
    texts.push(...rows.texts)
    unreadable.push(...rows.unreadable)
  }
  return { texts, unreadable }
}

/**
 * Splits `ledger.ts` into the claim values it renders, from both shapes it uses: a
 * field written as `name:` or `detail:`, and a value in the position a compact row
 * type labels as one. A field whose value cannot be read, or whose literal is only
 * part of a larger expression, is returned in `unreadable` and fails the check.
 */
function ledgerClaimTexts(source) {
  const texts = []
  const unreadable = []
  const starts = lineStarts(source)
  for (const match of source.matchAll(claimKey)) {
    const valueStart = match.index + match[0].length
    const line = lineAt(starts, match.index)
    const literal = readLiteral(source, valueStart)
    if (literal && endsValue(source, literal.end)) {
      texts.push({ line, text: literal.value })
      continue
    }
    const expression = expressionOnLine(source, valueStart)
    if (!primitiveAnnotation.test(expression)) {
      unreadable.push({ line, text: expression || match[0].trim() })
    }
  }
  const rows = rowClaimTexts(source)
  texts.push(...rows.texts)
  unreadable.push(...rows.unreadable)
  return { texts, unreadable }
}

/**
 * The escapes a JSON string may carry and the character each contributes. JSON
 * allows `/` where a JavaScript literal does not need it, and rejects the `\0`,
 * `\v`, `\'` and `` \` `` forms JavaScript accepts, so this map is JSON's own.
 */
const jsonEscapes = new Map([
  ['"', '"'],
  ['\\', '\\'],
  ['/', '/'],
  ['b', '\b'],
  ['f', '\f'],
  ['n', '\n'],
  ['r', '\r'],
  ['t', '\t'],
])

/**
 * The value a JSON escape sequence contributes and the index the scan resumes at,
 * after the whole sequence. `\uNNNN` is the only unicode form JSON allows; `\u{...}`
 * is JavaScript's. `null` means the sequence is not valid JSON, so the value that
 * holds it is uninspectable rather than read wrong.
 */
function readJsonEscape(source, index) {
  const char = source[index + 1]
  if (jsonEscapes.has(char)) return { value: jsonEscapes.get(char), next: index + 2 }
  if (char === 'u') return readFixedHexEscape(source, index + 2, 4)
  return null
}

/**
 * The JSON string token that opens at `start`, or `null` when it is unterminated or
 * carries an escape this reader cannot decode. A raw newline inside the token is
 * kept in the value: it makes the file invalid JSON, which is the validator's
 * finding, and the caller's line count still has to account for it.
 */
export function readJsonString(source, start) {
  let value = ''
  let index = start + 1
  while (index < source.length) {
    const char = source[index]
    if (char === '"') return { value, end: index + 1 }
    if (char === '\\') {
      const escape = readJsonEscape(source, index)
      if (escape === null) return null
      value += escape.value
      index = escape.next
      continue
    }
    value += char
    index += 1
  }
  return null
}

/**
 * The index of the first character from `index` that is not whitespace. JSON's
 * whitespace is the four ASCII characters `isWhitespace` names, so one test serves
 * both readers.
 */
function skipWhitespace(source, index) {
  let cursor = index
  while (cursor < source.length && isWhitespace(source[cursor])) cursor += 1
  return cursor
}

/**
 * Whether the string token that ends at `end` is an object key: the next
 * non-whitespace character is the `:` that separates the key from its value. A key
 * names a field; only a value is text a reader sees.
 */
const isJsonKey = (source, end) => source[skipWhitespace(source, end)] === ':'

/**
 * How many newlines `source` holds between `start` and `end`. A valid JSON string
 * holds none, so this is normally zero; counting them keeps the line numbers right
 * for a file that breaks that rule rather than shifting every later finding.
 */
function newlinesBetween(source, start, end) {
  let count = 0
  for (let cursor = start; cursor < end; cursor += 1) if (source[cursor] === '\n') count += 1
  return count
}

/**
 * The string values of a benchmark artifact, one entry per value at the line it
 * opens on. Keys are skipped and numbers are never read: the artifact's numbers are
 * schema-checked, and a sentence is what the prose rule covers. A token that cannot
 * be read stops the scan and is reported, so a malformed artifact fails the check
 * instead of passing unscanned.
 */
export function benchmarkClaimTexts(source) {
  const texts = []
  let cursor = 0
  let line = 1
  while (cursor < source.length) {
    const char = source[cursor]
    if (char !== '"') {
      line += char === '\n' ? 1 : 0
      cursor += 1
      continue
    }
    const token = readJsonString(source, cursor)
    if (token === null) return { texts, unreadable: [{ line, text: expressionOnLine(source, cursor) }] }
    if (!isJsonKey(source, token.end)) texts.push({ line, text: token.value })
    line += newlinesBetween(source, cursor, token.end)
    cursor = token.end
  }
  return { texts, unreadable: [] }
}

/**
 * The markup that ends a text node: a comment, a tag, or an interpolation. A
 * template renders a text node as the characters between two of these, so only
 * characters on the same side of one are joined. Two neighbouring elements are
 * never joined, and neither are the strings of a `<script>` block, because a tag
 * separates them: joining those would invent a phrase nobody wrote.
 *
 * Each is read leftmost first, a comment winning over the tag that shares its `<`
 * and a tag still matching when the comment does not close — `<!-->` is a tag —
 * which is what the three alternatives meant. It is walked rather than matched
 * because both patterns that express it are quadratic on a body with many openers
 * and no closing delimiter, the shape a half-written comment or a `{{` in prose
 * has. A lazy `[\s\S]*?` retries the rest of the body from every opener, and the
 * tempered `(?:[^-]|-(?!->))*` still does, because a backtracking engine re-enters
 * a repetition it already failed.
 *
 * The walk reads every character at most once: a position that starts no markup
 * costs one comparison and the cursor moves on, a position that starts markup jumps
 * the cursor past its close, and a closing delimiter — or a tag's `>` outside a
 * quoted attribute value — is resolved from a table computed once, so no search is
 * ever made that could run to the end without finding one.
 */
export function markupSpans(body) {
  const spans = []
  const bounds = {
    comment: body.lastIndexOf('-->'),
    tagEnd: tagEndOffsets(body),
    interpolation: body.lastIndexOf('}}'),
  }
  let cursor = 0
  while (cursor < body.length) {
    const char = body[cursor]
    const end = char === '<' || char === '{' ? markupEndAt(body, cursor, bounds) : -1
    if (end < 0) {
      cursor += 1
      continue
    }
    spans.push({ index: cursor, length: end - cursor })
    cursor = end
  }
  return spans
}

/**
 * Where the markup that opens at `at` ends, exclusive, or -1 when no delimiter
 * closes it. `bounds.comment` and `bounds.interpolation` hold the offset of the last
 * occurrence of their closer in the body, so a closer that does not exist after `at`
 * is never looked for: every search that is made finds its delimiter, and the
 * characters it reads are the ones the span then consumes. `bounds.tagEnd` holds, for
 * every offset, the `>` that ends a tag opened there — the first one outside a quoted
 * attribute value — so a `>` a value spells is text, not an end.
 */
function markupEndAt(body, at, bounds) {
  if (body[at] === '<') {
    if (at + 4 <= bounds.comment && body.startsWith('<!--', at)) return body.indexOf('-->', at + 4) + 3
    const end = bounds.tagEnd[at + 1]
    return end < 0 ? -1 : end + 1
  }
  const closes = at + 2 <= bounds.interpolation && body.startsWith('{{', at)
  return closes ? body.indexOf('}}', at + 2) + 2 : -1
}

/**
 * For every offset in `body`, the offset of the `>` that ends a tag opened there, or
 * -1 when no `>` closes it outside a quoted attribute value.
 *
 * A tag scan has three states — outside a value, inside a `"` value, inside a `'`
 * value — and all three are resolved in one backward pass, so ending a tag is a
 * lookup. That is what keeps the walk linear: a body full of unterminated quotes
 * cannot make every opener rescan the rest of the body, because no opener rescans
 * anything.
 */
function tagEndOffsets(body) {
  const states = {
    plain: new Int32Array(body.length + 1).fill(-1),
    double: new Int32Array(body.length + 1).fill(-1),
    single: new Int32Array(body.length + 1).fill(-1),
  }
  for (let index = body.length - 1; index >= 0; index -= 1) stepTagEnds(body, index, states)
  return states.plain
}

/**
 * Resolves the three quote states at `index` from the entries of the character after
 * it: a `>` ends the tag only outside a value, a `"` or `'` outside a value opens one,
 * and the matching quote returns to the unquoted state.
 */
function stepTagEnds(body, index, states) {
  const next = index + 1
  const char = body[index]
  if (char === '>') states.plain[index] = index
  else if (char === '"') states.plain[index] = states.double[next]
  else if (char === "'") states.plain[index] = states.single[next]
  else states.plain[index] = states.plain[next]
  states.double[index] = char === '"' ? states.plain[next] : states.double[next]
  states.single[index] = char === "'" ? states.plain[next] : states.single[next]
}

const templateOpenTag = '<template'
const templateCloseTag = '</template>'
const scriptOpenTag = '<script'
const tagNameEnd = /[\s>]/

/**
 * Whether the tag that opens at `at` is the element `name` rather than a longer name
 * that begins the same way.
 */
const opensElement = (source, at, name) => source.startsWith(name, at)
  && tagNameEnd.test(source[at + name.length] ?? '')

/**
 * Where the part of the file that opens at `at` ends, exclusive, when its characters
 * are not template markup: an HTML comment, or a `<script>` body. `-1` when `at`
 * opens neither.
 */
function nonTemplateBlockEnd(source, at) {
  if (source.startsWith('<!--', at)) {
    const end = source.indexOf('-->', at + 4)
    return end === -1 ? source.length : end + 3
  }
  if (!opensElement(source, at, scriptOpenTag)) return -1
  const end = source.indexOf('</script', at)
  return end === -1 ? source.length : end
}

/**
 * The template token that opens at `at`, or `null` when the `<` starts neither a
 * `<template>` nor a `</template>`, or the tag never closes. `end` is where the token
 * ends and `opens` says whether it opens or closes a block.
 */
function templateToken(source, at, tagEnd) {
  if (source.startsWith(templateCloseTag, at)) {
    return { at, end: at + templateCloseTag.length, opens: false }
  }
  if (!opensElement(source, at, templateOpenTag)) return null
  const end = tagEnd[at + 1]
  return end < 0 ? null : { at, end: end + 1, opens: true }
}

/**
 * Every template token in `source`, in order. HTML comments and `<script>` bodies are
 * skipped whole, so a `<template>` or `</template>` that a comment or a string spells
 * is not a token.
 */
function templateTokens(source) {
  const tokens = []
  const tagEnd = tagEndOffsets(source)
  let cursor = 0
  while (cursor < source.length) {
    const at = source.indexOf('<', cursor)
    if (at === -1) return tokens
    const blockEnd = nonTemplateBlockEnd(source, at)
    if (blockEnd !== -1) {
      cursor = blockEnd
      continue
    }
    const token = templateToken(source, at, tagEnd)
    if (token === null) {
      cursor = at + 1
      continue
    }
    tokens.push(token)
    cursor = token.end
  }
  return tokens
}

/**
 * A component's top-level template body and the offset it starts at, or `null` when
 * the file has no complete template block.
 *
 * The block is found by depth over the tokens, so a nested `<template v-if>` inside
 * the tree belongs to the region and cannot end it early. It is not found by the
 * file's last `</template>`: a `</template>` that an HTML comment or a `<script>`
 * string spells sits after the real close, and taking it would read the script as
 * prose — a script comment that splits a phrase over two lines then reports a claim
 * the page never renders.
 */
function templateRegion(source) {
  let depth = 0
  let start = -1
  for (const token of templateTokens(source)) {
    if (token.opens) {
      if (depth === 0) start = token.end
      depth += 1
      continue
    }
    if (depth === 0) continue
    depth -= 1
    if (depth === 0) return { start, body: source.slice(start, token.at) }
  }
  return null
}

/**
 * The half-open file offsets of every text run in a template body: the characters
 * between two pieces of markup, plus the run that follows the last one.
 */
function textRunOffsets(region) {
  const runs = []
  let last = region.start
  for (const markup of markupSpans(region.body)) {
    const at = region.start + markup.index
    runs.push({ from: last, to: at })
    last = at + markup.length
  }
  return [...runs, { from: last, to: region.start + region.body.length }]
}

/**
 * The character references a template may spell and the character each renders: the
 * numeric forms, decoded for any code point, and the named forms whose character a
 * rule reads — the spaces that join a phrase across a break, and the characters a
 * phrase is built from. A named reference outside this set is left as written,
 * because its character is not one any rule matches on.
 *
 * Both quantifiers are bounded. An HTML reference is short, and an unbounded run
 * would retry the rest of the text from every `&`, the polynomial shape this file
 * already had to remove once.
 */
const namedReferences = new Map([
  ['nbsp', '\u00a0'],
  ['ensp', '\u2002'],
  ['emsp', '\u2003'],
  ['thinsp', '\u2009'],
  ['amp', '&'],
  ['lt', '<'],
  ['gt', '>'],
  ['quot', '"'],
  ['apos', "'"],
])

const characterReference = /&(?:#(\d{1,7})|#[xX]([0-9a-fA-F]{1,6})|([a-zA-Z][a-zA-Z0-9]{0,31}));/g

/**
 * The character a character reference renders, or `null` when it names one this
 * checker does not read.
 */
function referenceValue(match) {
  const [, decimal, hexadecimal, name] = match
  if (name !== undefined) return namedReferences.get(name) ?? null
  const code = Number.parseInt(decimal ?? hexadecimal, decimal === undefined ? 16 : 10)
  return isCodePoint(code) ? String.fromCodePoint(code) : null
}

/**
 * The rendered characters of `source[run]` in order, each with the source range it
 * came from. A reference contributes one character over its whole spelling, so every
 * position a finding reports is the start of what produced the text.
 */
function textPieces(source, run) {
  const raw = source.slice(run.from, run.to)
  const pieces = []
  const plain = (from, to) => {
    for (let index = from; index < to; index += 1) {
      pieces.push({ text: raw[index], from: run.from + index, to: run.from + index + 1 })
    }
  }
  const decoded = (value, from, to) => {
    for (const unit of value.split('')) pieces.push({ text: unit, from, to })
  }
  let last = 0
  for (const match of raw.matchAll(characterReference)) {
    plain(last, match.index)
    const value = referenceValue(match)
    if (value === null) plain(match.index, match.index + match[0].length)
    else decoded(value, run.from + match.index, run.from + match.index + match[0].length)
    last = match.index + match[0].length
  }
  plain(last, raw.length)
  return pieces
}

const spaceCharacter = /\s/

/**
 * The text a node renders and the source offset of every character in it: each
 * whitespace run collapses to one space, the way a browser collapses it, and the
 * space keeps the start of the whole run. Whitespace at either end is dropped, as a
 * browser drops it.
 */
function collapsedText(pieces) {
  const out = []
  let space = null
  for (const piece of pieces) {
    if (spaceCharacter.test(piece.text)) {
      space = { text: ' ', from: space === null ? piece.from : space.from, to: piece.to }
      continue
    }
    if (space !== null && out.length > 0) out.push(space)
    space = null
    out.push(piece)
  }
  return {
    text: out.map(piece => piece.text).join(''),
    starts: out.map(piece => piece.from),
  }
}

/**
 * The prohibited phrases one node states, one per label, each at the line the phrase
 * starts on. A denial is decided against the node's whole clause, so a denial on one
 * source line excuses a claim the next line states, and an occurrence in a later
 * clause of the same node is still reported.
 */
function nodeOccurrences(model, lines) {
  const found = new Map()
  for (const match of phraseMatches(model.text)) {
    if (found.has(match.label)) continue
    found.set(match.label, { label: match.label, line: lineAt(lines, model.starts[match.start]) })
  }
  return [...found.values()]
}

/**
 * One template text node, read once: the text a browser renders — character
 * references decoded and whitespace runs collapsed — the line its text starts on,
 * and the phrases it states at the line each one starts on. `null` when the node
 * renders no text.
 */
function nodeModel(source, run, lines) {
  const model = collapsedText(textPieces(source, run))
  if (model.text === '') return null
  return {
    line: lineAt(lines, model.starts[0]),
    text: model.text,
    occurrences: nodeOccurrences(model, lines),
  }
}

/**
 * A component's rendered text nodes and the source ranges they cover, read once: the
 * line reader leaves those ranges to the node reader, which has the whole node.
 */
function templateModel(source, lines) {
  const region = templateRegion(source)
  if (region === null) return { entries: [], runs: [] }
  const runs = textRunOffsets(region)
  const entries = runs.map(run => nodeModel(source, run, lines)).filter(entry => entry !== null)
  return { entries, runs }
}

/**
 * Each line, with the template text runs it overlaps. The line reader skips an
 * occurrence inside one: the node reader reports it once, at the line the phrase
 * starts on, with the clause a single line cannot see.
 */
function withRuns(texts, runs, lines) {
  const covered = new Map()
  for (const run of runs) {
    if (run.from === run.to) continue
    const last = lineAt(lines, run.to - 1)
    for (let line = lineAt(lines, run.from); line <= last; line += 1) {
      covered.set(line, [...(covered.get(line) ?? []), run])
    }
  }
  return texts.map(text => (covered.has(text.line) ? { ...text, runs: covered.get(text.line) } : text))
}

/**
 * One scanned text per line, with its 1-based line number and the offset it starts
 * at, so a template text run can be matched to the lines it covers.
 */
export function lineTexts(source) {
  const starts = lineStarts(source)
  const texts = source.split(/\r?\n/).map((text, index) => ({ line: index + 1, text, offset: starts[index] }))
  return { texts, unreadable: [] }
}

/**
 * The text of a prose file: one entry per line, plus — in a single-file component —
 * the rendered text of every template text node. The node entries are merged back
 * into line order, so a file's findings are reported top to bottom however the scan
 * reached them.
 */
function proseTexts(file, source) {
  const lines = lineTexts(source)
  if (!file.endsWith('.vue')) return lines
  const starts = lineStarts(source)
  const template = templateModel(source, starts)
  const texts = [...withRuns(lines.texts, template.runs, starts), ...template.entries]
  // Sorted in place on its own statement: reporting in source order is the point,
  // and the array is a fresh local, so mutating it is intended rather than
  // incidental.
  texts.sort((left, right) => left.line - right.line)
  return { unreadable: [], texts }
}

/**
 * The text a rule runs against: every line of a prose file, the claim values of
 * `ledger.ts`, and the string values of a published benchmark artifact. The root is
 * a parameter so a fixture tree is scanned by this dispatch rather than by a copy
 * of it.
 */
export function scannedTexts(file, source, siteRoot = site) {
  if (file === join(siteRoot, layout.ledger)) return ledgerClaimTexts(source)
  if (file.startsWith(join(siteRoot, layout.benchmarks))) return benchmarkClaimTexts(source)
  return proseTexts(file, source)
}

/**
 * The prohibited phrases one scanned text states, each at the line it starts on: a
 * line or a claim value is one text on one line, and a template node carries the
 * lines its own occurrences start on.
 */
function phraseClaims(claimText) {
  if (claimText.occurrences !== undefined) return claimText.occurrences
  return lineLabels(claimText).map(label => ({ label, line: claimText.line }))
}

/**
 * The labels one line or claim value states. An occurrence the node reader owns is
 * left to it: the node reports it once, at the line its phrase starts on, and decides
 * a denial with the clause the line cannot see.
 */
function lineLabels(claimText) {
  const matches = phraseMatches(claimText.text).filter(match => !inNodeText(claimText, match))
  return [...new Set(matches.map(match => match.label))]
}

/**
 * Whether an occurrence lies inside a template text node, whose reader owns it.
 */
function inNodeText(claimText, match) {
  if (claimText.runs === undefined) return false
  const start = claimText.offset + match.start
  const end = claimText.offset + match.end
  return claimText.runs.some(run => run.from <= start && end <= run.to)
}

/**
 * Every violation of one scanned text, with the site-relative path the allowlist
 * names, so an entry and a violation point at the same file however the scan
 * reached it.
 */
function claimsForText(file, claimText, numericScope) {
  const text = claimText.text.trim()
  const phrases = phraseClaims(claimText).map(claim => ({ ...claim, token: null }))
  const numbers = numericScope
    ? numericViolations(claimText.text).map(claim => ({ ...claim, line: claimText.line }))
    : []
  return [...phrases, ...numbers].map(claim => ({ file, text, ...claim }))
}

function claimsForFile(file, texts, siteRoot = site) {
  const numericScope = file.startsWith(join(siteRoot, layout.data))
  const name = relative(siteRoot, file)
  return texts.flatMap(claimText => claimsForText(name, claimText, numericScope))
}

async function loadAllowlist() {
  if (!existsSync(allowlistPath)) return []
  const parsed = JSON.parse(await readFile(allowlistPath, 'utf8'))
  if (!Array.isArray(parsed.entries)) {
    console.error(`Claim check failed (1):\n  ${allowlistName} has no \`entries\` array`)
    process.exit(1)
  }
  return parsed.entries
}

/**
 * An entry must name the file and line it excuses and carry the exact numeric
 * token it exempts plus a reason; without those it is malformed rather than
 * merely stale. Each predicate holds at most one logical operator so no call site
 * becomes a complex conditional.
 */
const namesAFileAndLine = entry => isText(entry?.file) && Number.isInteger(entry?.line)
const hasTokenAndReason = entry => isFilledText(entry?.token) && isFilledText(entry?.reason)
const hasRequiredFields = entry => namesAFileAndLine(entry) && hasTokenAndReason(entry)

const isKnownFile = (entry, claim) => entry.file === claim.file
const isSameLine = (entry, claim) => entry.line === claim.line
const tokenMatches = (entry, claim) => claim.token !== null && entry.token === claim.token

/**
 * An entry excuses one occurrence: the numeric token at its own file and line,
 * matched exactly. A token that spans several numbers on one line matches no
 * single occurrence, so an entry wider than one claim is stale and fails.
 */
const matchesClaim = (entry, claim) => [
  isKnownFile(entry, claim),
  isSameLine(entry, claim),
  tokenMatches(entry, claim),
].every(Boolean)

/**
 * Every root the scan reads, paired with the filter that accepts its files. A prose
 * root holds one file per rendered page, `app/data` holds the typed claim data, and
 * `public/benchmarks` holds the published artifacts.
 */
function scanRoots(siteRoot = site) {
  return [
    ...layout.prose.map(root => ({ root: join(siteRoot, root), accept: proseFile })),
    { root: join(siteRoot, layout.data), accept: dataFile },
    { root: join(siteRoot, layout.benchmarks), accept: benchmarkFile },
  ]
}

/**
 * Every claim and every unreadable value under a site root.
 *
 * Every file is read once, concurrently, and then scanned in the same deterministic
 * order the walk produced. No callback awaits, so a slow file cannot serialise the
 * scan.
 */
export async function scan(siteRoot = site) {
  const roots = scanRoots(siteRoot)
  const files = (await Promise.all(roots.map(({ root, accept }) => walk(root, accept)))).flat()
  const sources = await Promise.all(files.map(file => readFile(file, 'utf8')))
  const scanned = files.map((file, index) => ({ file, ...scannedTexts(file, sources[index], siteRoot) }))
  const unreadable = scanned.flatMap(entry => entry.unreadable.map(item => ({
    file: relative(siteRoot, entry.file),
    line: item.line,
    label: unreadableLabel,
    text: item.text,
  })))
  const claims = scanned.flatMap(entry => claimsForFile(entry.file, entry.texts, siteRoot))
  return { unreadable, claims }
}

async function main() {
  const { unreadable, claims } = await scan(site)
  const allowlist = await loadAllowlist()
  const consumed = new Set()

  /**
   * The first unused, well-formed entry that excuses this occurrence is taken and
   * marked consumed, so a second occurrence cannot spend the same entry.
   */
  function takeAllowlistEntry(claim) {
    for (let index = 0; index < allowlist.length; index += 1) {
      if (consumed.has(index)) continue
      const entry = allowlist[index]
      if (!hasRequiredFields(entry)) continue
      if (matchesClaim(entry, claim)) {
        consumed.add(index)
        return true
      }
    }
    return false
  }

  function allowlistFailures() {
    const malformed = allowlist
      .filter(entry => !hasRequiredFields(entry))
      .map(entry => ({
        file: allowlistName,
        line: 0,
        label: 'malformed allowlist entry (needs file, line, token, reason)',
        text: JSON.stringify(entry),
      }))
    const stale = allowlist.flatMap((entry, index) => hasRequiredFields(entry) && !consumed.has(index)
      ? [{
        file: allowlistName,
        line: 0,
        label: 'stale allowlist entry (no numeric claim with that file, line, and token)',
        text: `${entry.file}:${entry.line} ${entry.token}`,
      }]
      : [])
    return [...malformed, ...stale]
  }

  /**
   * A phrase claim is never allowlisted; a numeric or score claim needs its own
   * entry. Consuming entries inside the filter is deliberate: it runs once per
   * claim, in file order, and leaves `consumed` ready for the staleness check.
   */
  const isFailure = claim => !allowlistableLabels.has(claim.label) || !takeAllowlistEntry(claim)
  const failures = [...unreadable, ...claims.filter(isFailure), ...allowlistFailures()]

  /**
   * A numeric failure names the exact token it objects to, because the allowlist
   * excuses one occurrence at a time and the line may hold several numbers.
   */
  const describeFailure = failure => (failure.token ? `${failure.label} [${failure.token}]` : failure.label)

  if (failures.length) {
    console.error(`Claim check failed (${failures.length}):`)
    for (const failure of failures) console.error(`  ${failure.file}:${failure.line} ${describeFailure(failure)}\n  ${failure.text}`)
    process.exit(1)
  }

  console.log('Claim check passed: no unsupported production, availability, or guarantee claims; every numeric claim names its artifact.')
}

/**
 * The scan runs only when this file is the entry point, so the readers above can be
 * imported and exercised directly. Both paths are resolved through the filesystem,
 * because comparing the URL form alone would miss a symlinked invocation and let the
 * check exit 0 without scanning anything.
 */
function invokedDirectly() {
  if (process.argv[1] === undefined) return false
  try {
    return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url))
  } catch {
    return false
  }
}

if (invokedDirectly()) await main()
