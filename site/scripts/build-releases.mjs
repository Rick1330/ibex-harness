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
  return text
    .replace(/\[([^\]]+)\]\(.+?\)/g, '$1')
    .replaceAll('**', '')
    .replace(/\s+/g, ' ')
    .trim()
}

for (const line of lines) {
  const release = line.match(/^## \[(.+?)\]\((.+?)\) \((\d{4}-\d{2}-\d{2})\)/)
  if (release) {
    current = { version: release[1], compareUrl: release[2], date: release[3], sections: [] }
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
    const issue = raw.match(/\(\[#(\d+)\]\((.+?)\)\)/)
    const commit = raw.match(/\(\[([0-9a-f]{7,40})\]\((.+?)\)\)/)
    let text = raw
      .replace(/\s*\(\[#\d+\]\(.+?\)\)/g, '')
      .replace(/\s*\(\[[0-9a-f]{7,40}\]\(.+?\)\)/g, '')
    text = clean(text)
    section.items.push({
      text,
      issue: issue ? { number: issue[1], url: issue[2] } : null,
      commit: commit ? { short: commit[1].slice(0, 7), url: commit[2] } : null,
    })
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

