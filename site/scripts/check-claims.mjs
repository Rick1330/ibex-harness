import { existsSync } from 'node:fs'
import { readFile, readdir } from 'node:fs/promises'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const site = resolve(here, '..')
const allowlistPath = join(here, 'claim-numbers.allowlist.json')

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

const denials = /\b(?:not|never|no|nor|none|isn't|aren't|without|avoid|rather than|beyond|cannot|can't|does not|do not|remains? open|gap)\b/i
const prohibited = [
  { pattern: /production[- ]ready/i, label: 'positive production-readiness claim' },
  { pattern: /battle[- ]tested/i, label: 'unsupported battle-tested claim' },
  { pattern: /enterprise[- ]grade/i, label: 'unsupported enterprise-grade claim' },
  { pattern: /five nines|99\.9+\s*%/i, label: 'unsupported availability number' },
  { pattern: /guaranteed\s+(?:uptime|latency|availability|isolation)/i, label: 'guarantee claim' },
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
const numericClaim = /(?<![A-Za-z0-9_.])(?:\d[\d,.]*\s*(?:%|ms|µs|ns)(?!\w)|p\d{2,3}(?!\w))/

/**
 * The artifact a quoted number must name on its own line: the benchmarks page,
 * a benchmark JSON file, a CI run, or a gold set.
 */
const artifactReference = /(?:\/benchmarks|benchmark-data|run\s+\d+|gold set)/i

const proseFile = name => /\.(?:md|vue)$/.test(name)
const dataFile = name => name.endsWith('.ts') && !name.endsWith('.test.ts')

async function walk(dir, accept) {
  const entries = await readdir(dir, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === 'adr' || entry.name === 'roadmap-archive') continue
      files.push(...await walk(full, accept))
    } else if (accept(entry.name)) {
      files.push(full)
    }
  }
  return files
}

/**
 * `ledger.ts` is code as well as claims: only the `name` and `detail` string
 * values are claims, so an object key or a derived count cannot trip a rule.
 */
const claimField = /(?:^|[\s{(,])(?:name|detail)\s*:\s*(['"])((?:\\.|(?!\1).)*)\1/g

function scannedLines(file, source) {
  const lines = source.split(/\r?\n/)
  if (file !== ledgerFile) return lines.map((text, index) => ({ number: index + 1, text }))
  return lines.flatMap((text, index) => [...text.matchAll(claimField)]
    .map(match => ({ number: index + 1, text: match[2] })))
}

function clauseBeforeMatch(line, index) {
  const before = line.slice(0, index)
  let cut = 0
  for (const match of before.matchAll(clauseBreaks)) cut = match.index + match[0].length
  return before.slice(cut)
}

function phraseViolations(line) {
  return prohibited.flatMap((rule) => {
    const match = rule.pattern.exec(line)
    if (!match || denials.test(clauseBeforeMatch(line, match.index))) return []
    return [rule.label]
  })
}

async function loadAllowlist() {
  if (!existsSync(allowlistPath)) return []
  const parsed = JSON.parse(await readFile(allowlistPath, 'utf8'))
  if (!Array.isArray(parsed.entries)) {
    console.error('Claim check failed (1):\n  claim-numbers.allowlist.json has no `entries` array')
    process.exit(1)
  }
  return parsed.entries
}

const isText = value => typeof value === 'string'
const isFilledText = value => isText(value) && value.length > 0

/**
 * An entry must name the file and line it excuses and carry the quoted text
 * plus a reason; without those it is malformed rather than merely stale.
 * Each predicate holds at most one logical operator so no call site becomes a
 * complex conditional.
 */
const namesAFileAndLine = entry => isText(entry?.file) && Number.isInteger(entry?.line)
const hasTextAndReason = entry => isFilledText(entry?.text) && isFilledText(entry?.reason)
const hasRequiredFields = entry => namesAFileAndLine(entry) && hasTextAndReason(entry)

const isKnownFile = (entry, claim) => entry.file === claim.file
const isSameLine = (entry, claim) => entry.line === claim.line
const textMatches = (entry, claim) => claim.text.includes(entry.text)

/**
 * An entry excuses only the claim at its own file, line, and text. The
 * conjunction is a list rather than an `&&` chain; the result is identical.
 */
const matchesClaim = (entry, claim) => [
  isKnownFile(entry, claim),
  isSameLine(entry, claim),
  textMatches(entry, claim),
].every(Boolean)

const allowlist = await loadAllowlist()
const consumed = new Set()

function markConsumed(index) {
  consumed.add(index)
}

/**
 * The first unused, well-formed entry that excuses this claim is taken and
 * marked consumed, so a second claim cannot spend the same entry.
 */
function takeAllowlistEntry(claim) {
  for (let index = 0; index < allowlist.length; index += 1) {
    if (consumed.has(index)) continue
    const entry = allowlist[index]
    if (!hasRequiredFields(entry)) continue
    if (matchesClaim(entry, claim)) {
      markConsumed(index)
      return true
    }
  }
  return false
}

const claims = []
for (const root of [...proseRoots, numericRoot]) {
  const accept = root === numericRoot ? dataFile : proseFile
  for (const file of await walk(root, accept)) {
    const numericScope = file.startsWith(numericRoot)
    for (const line of scannedLines(file, await readFile(file, 'utf8'))) {
      const labels = phraseViolations(line.text)
      if (numericScope && numericClaim.test(line.text) && !artifactReference.test(line.text)) {
        labels.push('numeric claim without an artifact reference')
      }
      for (const label of labels) {
        claims.push({ file: relative(site, file), line: line.number, label, text: line.text.trim() })
      }
    }
  }
}

const failures = claims.filter(claim =>
  claim.label !== 'numeric claim without an artifact reference' || !takeAllowlistEntry(claim))

for (const entry of allowlist) {
  if (!hasRequiredFields(entry)) {
    failures.push({ file: 'scripts/claim-numbers.allowlist.json', line: 0, label: 'malformed allowlist entry (needs file, line, text, reason)', text: JSON.stringify(entry) })
  }
}
allowlist.forEach((entry, index) => {
  if (hasRequiredFields(entry) && !consumed.has(index)) {
    failures.push({ file: 'scripts/claim-numbers.allowlist.json', line: 0, label: 'stale allowlist entry (file/line/text no longer match a numeric claim)', text: `${entry.file}:${entry.line} ${entry.text}` })
  }
})

if (failures.length) {
  console.error(`Claim check failed (${failures.length}):`)
  for (const failure of failures) console.error(`  ${failure.file}:${failure.line} ${failure.label}\n  ${failure.text}`)
  process.exit(1)
}

console.log('Claim check passed: no unsupported production, availability, or guarantee claims; every numeric claim names its artifact.')
