import { existsSync } from 'node:fs'
import { readFile, readdir } from 'node:fs/promises'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const site = resolve(here, '..')
const allowlistPath = join(here, 'claim-numbers.allowlist.json')
const allowlistName = 'scripts/claim-numbers.allowlist.json'

/**
 * Rendered prose: every page, docs page, and blog post.
 */
const proseRoots = ['app/pages', 'content/docs', 'content/blog'].map(root => join(site, root))

/**
 * Typed data: the claim-bearing strings a page renders and the numbers it plots.
 * A number a reader could take as a result is authored here or imported from a
 * committed artifact, so this is the surface the numeric-claim rule gates. Page
 * templates hold artifact values and static axis/label strings, not new results;
 * widening the numeric rule past this root would require an allowlist entry for
 * every documented target and every `pNN` field name in the docs tree.
 */
const numericRoot = join(site, 'app/data')
const ledgerFile = join(numericRoot, 'ledger.ts')

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
const unreadableLabel = 'claim value that cannot be inspected (needs a static string literal)'

const proseFile = name => /\.(?:md|vue)$/.test(name)
const dataFile = name => name.endsWith('.ts') && !name.endsWith('.test.ts')
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
 * The clause that contains `index`, as half-open offsets into `text`. The clause
 * starts after the last break before the match and ends at the first break after
 * it, so both a denial and a metric word are scoped to the claim they surround.
 */
function clauseBounds(text, index) {
  const breaks = [...text.matchAll(clauseBreaks)]
  let start = 0
  for (const match of breaks) {
    if (match.index + match[0].length <= index) start = match.index + match[0].length
  }
  const next = breaks.find(match => match.index >= index)
  return { start, end: next ? next.index : text.length }
}

const clauseBefore = (text, index) => text.slice(clauseBounds(text, index).start, index)

function clauseAround(text, index, length) {
  const { start, end } = clauseBounds(text, index)
  return text.slice(start, Math.max(end, index + length))
}

/**
 * Every occurrence of every prohibited pattern is evaluated on its own. A denial
 * excuses only the occurrence in its clause: "Not production-ready;
 * production-ready" has one denied and one undenied occurrence, so it fails.
 * Repeated labels collapse to one finding per scanned text.
 */
function phraseViolations(text) {
  const labels = prohibited.flatMap(rule => [...text.matchAll(rule.pattern)]
    .filter(match => !denials.test(clauseBefore(text, match.index)))
    .map(() => rule.label))
  return [...new Set(labels)]
}

const tokenClaims = (pattern, text, label, accept) => [...text.matchAll(pattern)]
  .filter(match => accept(match))
  .map(match => ({ label, token: match[0] }))

/**
 * A unitless score is a claim only when its own clause names the metric. A number
 * that carries a unit is not one: the measurement rule already reports it, so it
 * is dropped here rather than counted twice.
 */
function isScoreClaim(text, match) {
  const length = match[0].length
  if (carriesAUnit(text, match.index, length)) return false
  return scoreMetrics.test(clauseAround(text, match.index, length))
}

/**
 * Numeric claims, one finding per occurrence so the allowlist excuses one number
 * rather than the line it sits on. A line that names its artifact supports all
 * of its numbers and reports nothing.
 */
function numericViolations(text) {
  if (artifactReference.test(text)) return []
  const measures = tokenClaims(numericClaim, text, numericLabel, () => true)
  const scores = tokenClaims(dimensionlessScore, text, scoreLabel, match => isScoreClaim(text, match))
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

const lineOf = (source, index) => source.slice(0, index).split('\n').length

/**
 * Splits `ledger.ts` into the claim values it renders. A field whose value cannot
 * be read, or whose literal is only part of a larger expression, is returned in
 * `unreadable` and fails the check.
 */
function ledgerClaimTexts(source) {
  const texts = []
  const unreadable = []
  for (const match of source.matchAll(claimKey)) {
    const valueStart = match.index + match[0].length
    const line = lineOf(source, match.index)
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
  return { texts, unreadable }
}

/**
 * The text a rule runs against: every line of a prose file, and the claim values
 * of `ledger.ts`.
 */
function scannedTexts(file, source) {
  if (file !== ledgerFile) {
    return { texts: source.split(/\r?\n/).map((text, index) => ({ line: index + 1, text })), unreadable: [] }
  }
  return ledgerClaimTexts(source)
}

/**
 * Every violation of one scanned text, with the site-relative path the allowlist
 * names, so an entry and a violation point at the same file however the scan
 * reached it.
 */
function claimsForText(file, claimText, numericScope) {
  const { line } = claimText
  const text = claimText.text.trim()
  const phrases = phraseViolations(claimText.text).map(label => ({ label, token: null }))
  const numbers = numericScope ? numericViolations(claimText.text) : []
  return [...phrases, ...numbers].map(claim => ({ file, line, ...claim, text }))
}

function claimsForFile(file, texts) {
  const numericScope = file.startsWith(numericRoot)
  const name = relative(site, file)
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

const roots = [...proseRoots, numericRoot]
const files = (await Promise.all(roots.map(root =>
  walk(root, root === numericRoot ? dataFile : proseFile)))).flat()
const sources = await Promise.all(files.map(file => readFile(file, 'utf8')))

/**
 * Every file is read once, concurrently, and then scanned in the same
 * deterministic order the walk produced. No callback awaits, so a slow file
 * cannot serialise the scan.
 */
const scanned = files.map((file, index) => ({ file, ...scannedTexts(file, sources[index]) }))

const unreadable = scanned.flatMap(entry => entry.unreadable.map(item => ({
  file: relative(site, entry.file),
  line: item.line,
  label: unreadableLabel,
  text: item.text,
})))

const claims = scanned.flatMap(entry => claimsForFile(entry.file, entry.texts))

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
