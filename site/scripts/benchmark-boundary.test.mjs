import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { findWithheldSuiteLeaks, leakLines, withheldSuites } from './benchmark-boundary.mjs'

const { slug, artifact } = withheldSuites[0]

describe('leakLines', () => {
  it('flags a route, href, or sitemap mention of a withheld slug', () => {
    assert.deepEqual(
      leakLines(slug, artifact, [
        "const nav = [{ href: '/benchmarks/context-assembly' }]",
        "urls: ['/', '/benchmarks', '/benchmarks/context-assembly']",
      ].join('\n')),
      [1, 2],
    )
  })

  it('allows the data-contract artifact filename spelling', () => {
    assert.deepEqual(
      leakLines(slug, artifact, [
        `file: '${artifact}',`,
        `import data from '../../public/benchmarks/${artifact}'`,
        `export const runs = (${artifact}).runs`,
      ].join('\n')),
      [],
    )
  })
})

describe('withheld-suite boundary', () => {
  it('renders no withheld-suite link on any rendered surface', async () => {
    assert.deepEqual(await findWithheldSuiteLeaks(), [])
  })

  it('reports a content link to the withheld route as <file>:<line>', async () => {
    const root = await mkdtemp(join(tmpdir(), 'withheld-boundary-'))
    try {
      await mkdir(join(root, 'app'), { recursive: true })
      await writeFile(join(root, 'nuxt.config.ts'), 'export default {}\n')
      await mkdir(join(root, 'content/docs'), { recursive: true })
      await writeFile(join(root, 'content/docs/x.md'), [
        `inline: [docs](/benchmarks/${slug})`,
        `reference: [ref]: /benchmarks/${slug}`,
        `html: <a href="/benchmarks/${slug}">read</a>`,
        `absolute: https://ibexharness.com/benchmarks/${slug}#x`,
        `prose about context assembly`,
        `adr: 0038-context-assembly-service.md`,
        `blog: /blog/context-assembly-budget`,
        `data: /benchmarks/${artifact}`,
      ].join('\n'))
      await writeFile(join(root, 'content/docs/y.mdx'), [
        `mdx: [guide](/benchmarks/${slug})`,
      ].join('\n'))
      // readdir order across files is not guaranteed; compare the full set.
      assert.deepEqual([...(await findWithheldSuiteLeaks(root))].sort(), [
        'content/docs/x.md:1',
        'content/docs/x.md:2',
        'content/docs/x.md:3',
        'content/docs/x.md:4',
        'content/docs/y.mdx:1',
      ])
    } finally {
      await rm(root, { recursive: true, force: true })
    }
  })
})
