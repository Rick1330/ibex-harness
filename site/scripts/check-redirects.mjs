import { readFile, stat } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '../.output/public')
const redirectsFile = join(root, '_redirects')

async function exists(target) {
  try {
    await stat(target)
    return true
  } catch {
    return false
  }
}

async function routeExists(urlPath) {
  const clean = decodeURIComponent(urlPath.split('#')[0].split('?')[0])
  if (!clean.startsWith('/')) return false
  if (clean === '/') return exists(join(root, 'index.html'))
  const path = join(root, clean.slice(1))
  if (await exists(path)) {
    const info = await stat(path)
    if (!info.isDirectory()) return true
    if (await exists(join(path, 'index.html'))) return true
  }
  if (await exists(`${path}.html`)) return true
  if (await exists(join(path, 'index.html'))) return true
  return false
}

function isLocal(target) {
  return target.startsWith('/')
}

if (!await exists(redirectsFile)) {
  console.error(`Redirects file not found at ${redirectsFile}. Run pnpm build first.`)
  process.exit(1)
}

const lines = (await readFile(redirectsFile, 'utf8')).split(/\r?\n/)
const redirects = []
const failures = []

for (const [index, line] of lines.entries()) {
  const value = line.trim()
  if (!value || value.startsWith('#')) continue

  const [source, target, statusText] = value.split(/\s+/)
  if (!source || !target || !statusText) {
    failures.push(`line ${index + 1}: expected "source target status"`)
    continue
  }

  const status = Number(statusText)
  if (!Number.isInteger(status) || status < 300 || status > 399) {
    failures.push(`line ${index + 1}: invalid redirect status ${statusText}`)
    continue
  }

  redirects.push({ source, target, status, line: index + 1 })
}

const sources = new Map()
for (const redirect of redirects) {
  sources.set(redirect.source, (sources.get(redirect.source) ?? 0) + 1)
}

const localSources = new Set(redirects.filter(({ source }) => isLocal(source)).map(({ source }) => source))

for (const redirect of redirects) {
  const { source, target, line } = redirect

  if (sources.get(source) > 1) {
    failures.push(`line ${line}: duplicate source ${source}`)
  }

  if (isLocal(source)) {
    const concreteSource = source.endsWith('*') ? source.slice(0, -1) : source
    if (concreteSource !== '/' && await routeExists(concreteSource)) {
      failures.push(`line ${line}: source ${source} shadows a built page`)
    }
  }

  if (!isLocal(target)) {
    try {
      const url = new URL(target)
      if (url.protocol !== 'https:') failures.push(`line ${line}: external target must use https (${target})`)
    } catch {
      failures.push(`line ${line}: invalid external target ${target}`)
    }
    continue
  }

  if (target.includes('*')) {
    const prefix = target.slice(0, target.indexOf('*'))
    if (!await routeExists(prefix)) {
      failures.push(`line ${line}: wildcard target ${target} has no resolvable prefix`)
    }
    continue
  }

  if (!await routeExists(target)) {
    failures.push(`line ${line}: target ${target} does not resolve in the build output`)
  }

  if (localSources.has(target)) {
    failures.push(`line ${line}: target ${target} is another redirect; avoid redirect chains`)
  }

  if (source.includes('*') && target === source) {
    failures.push(`line ${line}: redirect loop from ${source} to ${target}`)
  }
}

if (failures.length) {
  console.error(`Invalid redirects (${failures.length}):`)
  for (const failure of failures) console.error(`  ${failure}`)
  process.exit(1)
}

console.log(`Checked ${redirects.length} redirects; sources, targets, and status codes are valid.`)
