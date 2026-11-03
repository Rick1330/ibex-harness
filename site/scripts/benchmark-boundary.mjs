import { readFile, readdir, stat } from 'node:fs/promises'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const site = resolve(here, '..')

/**
 * Suites registered in app/data/benchmarks.ts whose Overview page route does
 * not exist: no rendered surface may link, card, navigate, or sitemap the
 * suite, and its slug may appear in a rendered source only inside the
 * data-contract artifact filename.
 */
export const withheldSuites = [
  { slug: 'context-assembly', artifact: 'context-assembly-benchmark-data.json' },
]

/**
 * Line numbers (1-based) of the rendered-source lines that mention a withheld
 * slug anywhere outside its data-contract artifact filename — i.e. a route,
 * href, card, nav item, or sitemap entry for a page that does not exist.
 */
export function leakLines(slug, artifact, source) {
  const stripped = source.replaceAll(artifact, '')
  return stripped
    .split(/\r?\n/)
    .flatMap((line, index) => line.includes(slug) ? [index + 1] : [])
}

/**
 * Line numbers (1-based) of the markdown lines whose link destination is the
 * withheld route itself: `/benchmarks/<slug>` with no `[\w-]` character
 * immediately after, so the artifact filename and sibling slugs (blog posts,
 * ADR files) never match. Inline links, reference-style definitions,
 * MDC/HTML `href` and absolute site URLs all carry the route verbatim, so
 * one pattern covers them.
 */
function contentLeakLines(slug, source) {
  const route = new RegExp(String.raw`/benchmarks/${slug}(?![\w-])`)
  return source
    .split(/\r?\n/)
    .flatMap((line, index) => route.test(line) ? [index + 1] : [])
}

/**
 * Every file under `entry`, recursing through directories; a single file
 * passes through unchanged.
 */
async function walk(entry) {
  const info = await stat(entry)
  if (!info.isDirectory()) return [entry]
  const entries = await readdir(entry)
  return (await Promise.all(entries.map((name) => walk(join(entry, name))))).flat()
}

/**
 * The scanned files of a surface with their sources, read up front so the
 * scan pass over the pairs stays synchronous — no `await` inside a loop.
 */
async function collectScanFiles(entries, pattern) {
  const files = (await Promise.all(entries.map(walk)))
    .flat()
    .filter((file) => pattern.test(file))
  return Promise.all(
    files.map(async (file) => ({ file, source: await readFile(file, 'utf8') })),
  )
}

/**
 * Leak lines across every rendered surface: the app sources (.vue/.ts under
 * site/app — landing page, components, nav, data) plus nuxt.config.ts, whose
 * `sitemap.urls` is the sitemap surface, and the markdown under site/content,
 * whose docs and blog pages are prerendered output. site/e2e is browser-test
 * code, not a rendered surface, so it is not scanned.
 */
export async function findWithheldSuiteLeaks(siteRoot = site) {
  const rendered = await collectScanFiles(
    [join(siteRoot, 'app'), join(siteRoot, 'nuxt.config.ts')],
    /\.(?:vue|ts)$/,
  )
  const content = await collectScanFiles([join(siteRoot, 'content')], /\.mdx?$/)

  const renderedLeaks = rendered.flatMap(({ file, source }) =>
    withheldSuites.flatMap(({ slug, artifact }) =>
      leakLines(slug, artifact, source).map(
        (line) => `${relative(siteRoot, file)}:${line}`,
      ),
    ),
  )
  const contentLeaks = content.flatMap(({ file, source }) =>
    withheldSuites.flatMap(({ slug }) =>
      contentLeakLines(slug, source).map(
        (line) => `${relative(siteRoot, file)}:${line}`,
      ),
    ),
  )
  return [...renderedLeaks, ...contentLeaks]
}
