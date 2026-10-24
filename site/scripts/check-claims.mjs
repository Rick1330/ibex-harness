import { readFile, readdir } from 'node:fs/promises'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const site = resolve(here, '..')
const roots = [join(site, 'app/pages'), join(site, 'content/docs'), join(site, 'content/blog')]

const denials = /\b(?:not|never|no|none|isn't|aren't|without|avoid|rather than|beyond|cannot|can't|does not|do not|remains? open|gap)\b/i
const prohibited = [
  { pattern: /production[- ]ready/i, label: 'positive production-readiness claim' },
  { pattern: /battle[- ]tested/i, label: 'unsupported battle-tested claim' },
  { pattern: /enterprise[- ]grade/i, label: 'unsupported enterprise-grade claim' },
  { pattern: /five nines|99\.9+\s*%/i, label: 'unsupported availability number' },
  { pattern: /guaranteed\s+(?:uptime|latency|availability|isolation)/i, label: 'guarantee claim' },
]

async function walk(dir) {
  const entries = await readdir(dir, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === 'adr' || entry.name === 'roadmap-archive') continue
      files.push(...await walk(full))
    } else if (/\.(?:md|vue)$/.test(entry.name)) {
      files.push(full)
    }
  }
  return files
}

const failures = []
for (const root of roots) {
  for (const file of await walk(root)) {
    const lines = (await readFile(file, 'utf8')).split(/\r?\n/)
    lines.forEach((line, index) => {
      for (const rule of prohibited) {
        if (rule.pattern.test(line) && !denials.test(line)) {
          failures.push(`${relative(site, file)}:${index + 1} ${rule.label}\n  ${line.trim()}`)
        }
      }
    })
  }
}

if (failures.length) {
  console.error(`Claim check failed (${failures.length}):`)
  for (const failure of failures) console.error(`  ${failure}`)
  process.exit(1)
}

console.log('Claim check passed: no unsupported production, availability, or guarantee claims.')
