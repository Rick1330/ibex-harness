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
 */
const clauseBreaks = /[.;,!?:]|\b(?:but|however|yet|although|though|while)\b/gi

/**
 * A number that reads as a measurement: a digit with a unit suffix, or a
 * percentile token. Field names such as `latency_ms_p95` and bare versions such
 * as `v1` are not claims.
 */
const numericClaim = /(?<![A-Za-z0-9_.])(?:\d[\d,.]*\s*(?:%|ms|µs|ns)(?!\w)|p\d{2,3}(?!\w))/g

/**
 * A number that reads as a result without carrying a unit: a bare score such as
 * `0.99` or `.97`. It is a claim only when its own clause names the metric it
 * measures. The lookbehind keeps `routing_0.5` a field name and the lookaheads
 * keep `1.0.9` a version, `.9` the tail of that version, and `99.9%` or `1.5 ms`
 * the percentage and time-unit claims the rule above already reports. It is gated
 * by the same `app/data` scope as those claims, where a reader-facing result is
 * authored.
 */
const dimensionlessScore = /(?<![A-Za-z0-9_.])(?:0?\.\d+|\d+\.\d+)(?!\d)(?!\.\d)(?!\s*(?:%|ms|µs|ns)\b)/g
const scoreMetrics = /\b(?:mrr|precision|recall|ndcg|accuracy|f1|scores?|p50|p95|p99)\b/i

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
 * Numeric claims, one finding per occurrence so the allowlist excuses one number
 * rather than the line it sits on. A line that names its artifact supports all
 * of its numbers and reports nothing.
 */
function numericViolations(text) {
  if (artifactReference.test(text)) return []
  const measures = tokenClaims(numericClaim, text, numericLabel, () => true)
  const scores = tokenClaims(dimensionlessScore, text, scoreLabel,
    match => scoreMetrics.test(clauseAround(text, match.index, match[0].length)))
  return [...measures, ...scores]
}

/**
 * `ledger.ts` is code as well as claims: only the `name` and `detail` string
 * values are claims, so an object key or a derived count cannot trip a rule.
 * A claim field is read from a single-quoted, double-quoted, or template literal,
 * on one line or several.
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
 * Escapes a literal may carry. Anything else resolves to the character itself,
 * which is enough to read a claim: the checker compares prose, not byte values.
 */
const escapeMap = new Map([['n', '\n'], ['r', '\r'], ['t', '\t']])
const unescapeChar = char => escapeMap.get(char) ?? char ?? ''

/**
 * Reads the literal that starts at `start`. `null` means the value is not a
 * static string: unterminated, a single-line literal that breaks across lines, or
 * a template with `${}` interpolation, whose runtime text is not in the source.
 */
function readLiteral(source, start) {
  const quote = source[start]
  const template = quote === '`'
  let value = ''
  for (let index = start + 1; index < source.length; index += 1) {
    const char = source[index]
    if (template && char === '$' && source[index + 1] === '{') return null
    if (char === '\\') {
      value += unescapeChar(source[index + 1])
      index += 1
      continue
    }
    if (char === quote) return { value, end: index + 1 }
    if (!template && char === '\n') return null
    value += char
  }
  return null
}

const lineOf = (source, index) => source.slice(0, index).split('\n').length

/**
 * Splits `ledger.ts` into the claim values it renders. A field whose value cannot
 * be read is returned in `unreadable` and fails the check.
 */
function ledgerClaimTexts(source) {
  const texts = []
  const unreadable = []
  for (const match of source.matchAll(claimKey)) {
    const valueStart = match.index + match[0].length
    const line = lineOf(source, match.index)
    const literal = readLiteral(source, valueStart)
    if (literal) {
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
