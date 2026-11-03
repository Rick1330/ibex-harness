import { readFile, readdir, stat } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '../.output/public')

async function exists(target) {
  try {
    await stat(target)
    return true
  } catch {
    return false
  }
}

async function walk(dir) {
  const entries = await readdir(dir, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) files.push(...await walk(full))
    else files.push(full)
  }
  return files
}

if (!await exists(root)) {
  console.error(`Build output not found at ${root}. Run pnpm build first.`)
  process.exit(1)
}

const files = await walk(root)
const htmlFiles = files.filter(file => file.endsWith('.html'))
const targets = new Map()
const failures = []

function decode(value) {
  return value
    .replaceAll('&amp;', '&')
    .replaceAll('&quot;', '"')
    .replaceAll('&#39;', "'")
    .replaceAll('&lt;', '<')
    .replaceAll('&gt;', '>')
}

function publicPath(file) {
  return `/${file.slice(root.length + 1).replaceAll('\\', '/')}`
}

async function resolves(urlPath) {
  const clean = decode(urlPath.split('#')[0].split('?')[0])
  if (!clean.startsWith('/')) return true
  if (clean === '/') return exists(join(root, 'index.html'))
  const path = join(root, clean.slice(1))
  if (await exists(path)) {
    const info = await stat(path)
    if (!info.isDirectory()) return true
    if (await exists(join(path, 'index.html'))) return true
  }
  if (await exists(`${path}.html`)) return true
  return false
}

for (const file of htmlFiles) {
  const html = await readFile(file, 'utf8')
  const page = publicPath(file)
  for (const match of html.matchAll(/\s(?:href|src)="([^"]+)"/g)) {
    const raw = match[1]
    if (!raw || raw.startsWith('#') || /^(?:https?:|mailto:|tel:|data:|javascript:)/.test(raw)) continue
    if (!raw.startsWith('/')) {
      failures.push(`${page} -> ${raw} (non-absolute internal link)`)
      continue
    }
    if (!targets.has(raw)) targets.set(raw, await resolves(raw))
    if (!targets.get(raw)) failures.push(`${page} -> ${raw}`)
  }
}

if (failures.length) {
  console.error(`Broken internal links (${failures.length}):`)
  for (const failure of failures) console.error(`  ${failure}`)
  process.exit(1)
}

console.log(`Checked ${htmlFiles.length} HTML files; all internal links resolve.`)
