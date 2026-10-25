import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '../..')
const source = resolve(root, 'CHANGELOG.md')
const target = resolve(here, '../app/data/releases.json')
const rssTarget = resolve(here, '../public/releases.xml')

const markdown = await readFile(source, 'utf8')
const lines = markdown.split(/\r?\n/)

const releases = []
let current = null
let section = null

function clean(text) {
  return stripMarkdownLinks(text)
    .replaceAll('**', '')
    .replace(/\s+/g, ' ')
    .trim()
}

// Markdown link "[label](url)" -> "label", located with indexOf so no
// backtracking regex runs over changelog text.
function stripMarkdownLinks(text) {
  let out = ''
  let cursor = 0
  for (;;) {
    const labelStart = text.indexOf('[', cursor)
    if (labelStart === -1) break
    const labelEnd = text.indexOf('](', labelStart + 1)
    if (labelEnd === -1) break
    const urlEnd = text.indexOf(')', labelEnd + 2)
    if (urlEnd === -1) break
    out += text.slice(cursor, labelStart) + text.slice(labelStart + 1, labelEnd)
    cursor = urlEnd + 1
  }
  return out + text.slice(cursor)
}

// Release headings look like "## [1.2.3](compare-url) (2026-10-01)".
function parseReleaseHeading(line) {
  if (!line.startsWith('## [')) return null
  const versionEnd = line.indexOf('](')
  if (versionEnd === -1) return null
  const urlEnd = line.indexOf(') (', versionEnd + 2)
  if (urlEnd === -1) return null
  const date = line.slice(urlEnd + 3, urlEnd + 13)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null
  return { version: line.slice(3, versionEnd), compareUrl: line.slice(versionEnd + 2, urlEnd), date }
}

// Issue references look like "(#[123](https://...))"; commit references look
// like "([abc1234](https://...))". Returns the parts and the line without them.
function parseTrailingReference(raw) {
  const open = raw.lastIndexOf('([')
  if (open === -1 || !raw.endsWith('))')) return { text: raw, match: null }
  const close = raw.length - 2
  const bracketEnd = raw.indexOf('](', open + 2)
  if (bracketEnd === -1 || bracketEnd > close) return { text: raw, match: null }
  const label = raw.slice(open + 2, bracketEnd)
  const url = raw.slice(bracketEnd + 2, close)
  return { text: raw.slice(0, open).trimEnd(), match: { label, url } }
}

function isCommitLabel(label) {
  return /^[0-9a-f]{7,40}$/.test(label)
}

for (const line of lines) {
  const release = parseReleaseHeading(line)
  if (release) {
    current = { version: release.version, compareUrl: release.compareUrl, date: release.date, sections: [] }
    releases.push(current)
    section = null
    continue
  }
  if (!current) continue

  const heading = line.match(/^### (.+)$/)
  if (heading) {
    const title = heading[1].trim()
    section = current.sections.find(existing => existing.title === title)
    if (!section) {
      section = { title, items: [] }
      current.sections.push(section)
    }
    continue
  }

  const item = line.match(/^\* (.+)$/)
  if (item && section) {
    const raw = item[1].trim()
    const reference = parseTrailingReference(raw)
    /** @type {{ number: string, url: string } | null} */
    let issue = null
    /** @type {{ short: string, url: string } | null} */
    let commit = null
    if (reference.match) {
      if (reference.match.label.startsWith('#')) {
        issue = { number: reference.match.label.slice(1), url: reference.match.url }
      } else if (isCommitLabel(reference.match.label)) {
        commit = { short: reference.match.label.slice(0, 7), url: reference.match.url }
      }
    }
    const text = clean(reference.text)
    section.items.push({ text, issue, commit })
  }
}

for (const release of releases) {
  release.sections = release.sections.filter(section => section.items.length > 0)
}

function xml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll('\'', '&apos;')
}

const items = releases.slice(0, 20).map((release) => {
  const description = release.sections
    .map(section => `${section.title}: ${section.items.map(item => item.text).join('; ')}`)
    .join('\n')
  return `    <item>
      <title>IBEX Harness v${xml(release.version)}</title>
      <link>https://github.com/Rick1330/ibex-harness/releases/tag/v${xml(release.version)}</link>
      <guid isPermaLink="false">ibex-harness-v${xml(release.version)}</guid>
      <pubDate>${new Date(`${release.date}T12:00:00Z`).toUTCString()}</pubDate>
      <description>${xml(description)}</description>
    </item>`
}).join('\n')

const rss = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>IBEX Harness releases</title>
    <link>https://ibexharness.com/releases</link>
    <description>Release notes generated from the IBEX Harness changelog.</description>
    <language>en</language>
    <lastBuildDate>${releases[0] ? new Date(`${releases[0].date}T12:00:00Z`).toUTCString() : new Date().toUTCString()}</lastBuildDate>
${items}
  </channel>
</rss>
`

await mkdir(dirname(target), { recursive: true })
await writeFile(target, `${JSON.stringify(releases, null, 2)}\n`)
await writeFile(rssTarget, rss)
console.log(`Wrote ${releases.length} releases to ${target} and ${rssTarget}`)

