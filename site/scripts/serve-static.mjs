// Static server for local browser gates. Cloudflare Pages deploys only
// .output/public, so the e2e suite must exercise exactly that artifact —
// not the Nitro Node server, which can answer routes the deployment cannot.
// Mirrors the Pages behavior the site relies on: _redirects rules evaluated
// before static assets, directory index.html resolution, and a 404 page.
import { createServer } from 'node:http'
import { readFile, stat } from 'node:fs/promises'
import { dirname, extname, join, normalize, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '../.output/public')
const host = process.env.HOST || '127.0.0.1'
const port = Number(process.env.PORT || 3282)

const contentTypes = new Map([
  ['.html', 'text/html; charset=utf-8'],
  ['.css', 'text/css; charset=utf-8'],
  ['.js', 'text/javascript; charset=utf-8'],
  ['.mjs', 'text/javascript; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.xml', 'application/xml; charset=utf-8'],
  ['.txt', 'text/plain; charset=utf-8'],
  ['.md', 'text/markdown; charset=utf-8'],
  ['.svg', 'image/svg+xml'],
  ['.png', 'image/png'],
  ['.jpg', 'image/jpeg'],
  ['.jpeg', 'image/jpeg'],
  ['.webp', 'image/webp'],
  ['.avif', 'image/avif'],
  ['.ico', 'image/x-icon'],
  ['.woff2', 'font/woff2'],
  ['.webmanifest', 'application/manifest+json'],
  ['.map', 'application/json; charset=utf-8'],
  ['.wasm', 'application/wasm'],
])

const redirects = []

async function loadRedirects() {
  let raw
  try {
    raw = await readFile(join(root, '_redirects'), 'utf8')
  } catch {
    return
  }
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const [source, target, status] = trimmed.split(/\s+/)
    if (!source || !target) continue
    redirects.push({ source, target, status: status ?? '301' })
  }
}

// Cloudflare Pages semantics: a matching rule wins over static assets, which
// is why no blanket /benchmarks/* rule may ever be added while JSON files live
// in site/public/benchmarks.
function matchRedirect(pathname) {
  for (const rule of redirects) {
    if (rule.source.endsWith('/*')) {
      const prefix = rule.source.slice(0, -2)
      if (pathname === prefix || pathname.startsWith(`${prefix}/`)) {
        const splat = pathname.slice(prefix.length)
        return { target: rule.target.replace(':splat', splat), status: rule.status }
      }
    } else if (rule.source === pathname) {
      return { target: rule.target, status: rule.status }
    }
  }
  return null
}

async function fileExists(path) {
  try {
    return (await stat(path)).isFile()
  } catch {
    return false
  }
}

async function resolveAsset(urlPath) {
  const clean = normalize(decodeURIComponent(urlPath)).replace(/^(\.\.[/\\])+/, '')
  const base = join(root, clean)
  if (await fileExists(base)) return base
  if (await fileExists(`${base}.html`)) return `${base}.html`
  if (await fileExists(join(base, 'index.html'))) return join(base, 'index.html')
  return null
}

function isRedirect(match) {
  return match !== null && (match.status === '301' || match.status === '302')
}

async function resolveServedAsset(match, pathname) {
  if (match && match.status === '200') return resolveAsset(match.target)
  return resolveAsset(pathname)
}

async function handle(request, response) {
  const pathname = new URL(request.url, `http://${request.headers.host}`).pathname
  const match = matchRedirect(pathname)

  if (isRedirect(match)) {
    response.writeHead(Number(match.status), { Location: match.target })
    response.end()
    return
  }

  const asset = await resolveServedAsset(match, pathname)
  if (asset) {
    const body = await readFile(asset)
    response.writeHead(200, { 'Content-Type': contentTypes.get(extname(asset)) ?? 'application/octet-stream' })
    response.end(body)
    return
  }

  await serveNotFound(response)
}

async function serveNotFound(response) {
  const notFound = await resolveAsset('/404.html')
  if (notFound) {
    const body = await readFile(notFound)
    response.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' })
    response.end(body)
    return
  }
  response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' })
  response.end('Not found')
}

await loadRedirects()

createServer((request, response) => {
  handle(request, response).catch(() => {
    response.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' })
    response.end('Internal server error')
  })
}).listen(port, host, () => {
  console.log(`Serving ${root} on http://${host}:${port}`)
})
