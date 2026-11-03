import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '../..')
const source = resolve(root, 'CHANGELOG.md')
const target = resolve(here, '../app/data/releases.json')
const rssTarget = resolve(here, '../public/releases.xml')

// Markdown link "[label](url)" -> "label", located with indexOf so no
// backtracking regex runs over changelog text (S5852).
export function stripMarkdownLinks(text) {
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

export function clean(text) {
  return stripMarkdownLinks(text)
    .replaceAll('**', '')
    .replace(/\s+/g, ' ')
    .trim()
}

// Release headings look like "## [1.2.3](compare-url) (2026-10-01)"; the
// version starts after "## [" at index 4.
export function parseReleaseHeading(line) {
  if (!line.startsWith('## [')) return null
  const versionEnd = line.indexOf('](')
  if (versionEnd === -1) return null
  const urlEnd = line.indexOf(') (', versionEnd + 2)
  if (urlEnd === -1) return null
  const date = line.slice(urlEnd + 3, urlEnd + 13)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null
  return { version: line.slice(4, versionEnd), compareUrl: line.slice(versionEnd + 2, urlEnd), date }
}

export function isCommitLabel(label) {
  return /^[0-9a-f]{7,40}$/.test(label)
}

// Item entries may end with an issue reference "([#911](https://...))" and/or
// a commit reference "([2411f73](https://...))". Extract them from the end
// inward so both survive; the remaining text is cleaned separately.
export function parseTrailingReference(raw) {
  const refs = { issue: null, commit: null }
  let text = raw
  for (;;) {
    const open = text.lastIndexOf('([')
    if (open === -1 || !text.endsWith('))')) break
    const close = text.length - 2
    const bracketEnd = text.indexOf('](', open + 2)
    if (bracketEnd === -1 || bracketEnd > close) break
    const label = text.slice(open + 2, bracketEnd)
    const url = text.slice(bracketEnd + 2, close)
    if (label.startsWith('#')) {
      refs.issue = { number: label.slice(1), url }
    } else if (isCommitLabel(label)) {
      refs.commit = { short: label.slice(0, 7), url }
    } else {
      break
    }
    text = text.slice(0, open).trimEnd()
  }
  return { text, refs }
}

export function parseChangelog(markdown) {
  const lines = markdown.split(/\r?\n/)
  const releases = []
  let current = null
  let section = null

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
      const { text: stripped, refs } = parseTrailingReference(raw)
      const text = clean(stripped)
      section.items.push({ text, issue: refs.issue, commit: refs.commit })
    }
  }

  for (const release of releases) {
    release.sections = release.sections.filter(section => section.items.length > 0)
  }
  return releases
}

function xml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll('\'', '&apos;')
}

export function buildRss(releases) {
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

  return `<?xml version="1.0" encoding="UTF-8"?>
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
}

async function main() {
  const markdown = await readFile(source, 'utf8')
  const releases = parseChangelog(markdown)

  await mkdir(dirname(target), { recursive: true })
  await writeFile(target, `${JSON.stringify(releases, null, 2)}\n`)
  await writeFile(rssTarget, buildRss(releases))
  console.log(`Wrote ${releases.length} releases to ${target} and ${rssTarget}`)
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href
if (isMain) {
  await main()
}
