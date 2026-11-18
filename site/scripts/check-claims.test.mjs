import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import {
  benchmarkClaimTexts,
  phraseViolations,
  readJsonString,
  scan,
  scannedTexts,
  unreadableLabel,
} from './check-claims.mjs'

/**
 * Every root `scan` reads. A fixture must hold all of them, because the scan walks
 * the declared layout rather than only the directories a test happens to write.
 */
const roots = [
  'app/pages',
  'content/docs',
  'content/blog',
  'app/components',
  'app/data',
  'public/benchmarks',
]

/**
 * A throwaway site tree holding `files`, handed to `run` and removed afterwards.
 */
async function withSite(files, run) {
  const root = await mkdtemp(join(tmpdir(), 'claim-check-'))
  try {
    await Promise.all(roots.map(directory => mkdir(join(root, directory), { recursive: true })))
    await Promise.all(Object.entries(files).map(async ([path, source]) => {
      await mkdir(join(root, path, '..'), { recursive: true })
      await writeFile(join(root, path), source)
    }))
    return await run(root)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
}

describe('the JSON string reader', () => {
  it('decodes a \\u escape, so a spelled-around phrase reads as the phrase', () => {
    // A prohibited phrase hidden behind an escape renders as the phrase, so passing
    // the raw source through would miss the claim the reader sees.
    assert.deepEqual(readJsonString(String.raw`"guarant\u0065ed uptime"`, 0), {
      value: 'guaranteed uptime',
      end: 24,
    })
  })

  it('returns null for an escape JSON does not allow rather than guessing the text', () => {
    assert.equal(readJsonString(String.raw`"a\x41"`, 0), null)
  })

  it('returns null for a string that never closes', () => {
    assert.equal(readJsonString('"unterminated', 0), null)
  })
})

describe('a benchmark artifact', () => {
  it('reports a prohibited phrase that is spelled out with escapes', () => {
    const { texts, unreadable } = benchmarkClaimTexts(String.raw`{"note": "guarant\u0065ed uptime"}`)
    assert.deepEqual(unreadable, [])
    assert.deepEqual(texts, [{ line: 1, text: 'guaranteed uptime' }])
    assert.deepEqual(phraseViolations(texts[0].text), ['guarantee claim'])
  })

  it('does not scan an object key as a claim', () => {
    // A key names a field and only a value is text a reader sees, so a prohibited
    // phrase in a key is not a claim a page renders. Pinned so the decision is not
    // reversed by accident.
    const { texts } = benchmarkClaimTexts('{"guaranteed uptime": "measured"}')
    assert.deepEqual(texts, [{ line: 1, text: 'measured' }])
  })

  it('puts each value on the line it opens on, not on the line the file starts', () => {
    const source = [
      '{',
      '  "suite": "gold-set",',
      '  "note": "a note",',
      '  "claim": "production-ready",',
      '}',
    ].join('\n')
    assert.deepEqual(benchmarkClaimTexts(source).texts, [
      { line: 2, text: 'gold-set' },
      { line: 3, text: 'a note' },
      { line: 4, text: 'production-ready' },
    ])
  })

  it('keeps the line count right when a value broke the no-newline rule', () => {
    // An invalid artifact is the validator's finding, but a raw newline inside a
    // string must not shift every later finding onto the wrong line.
    const source = '{"a": "one\ntwo", "b": "production-ready"}'
    assert.equal(benchmarkClaimTexts(source).texts[1].line, 2)
  })

  it('reports a value it cannot decode instead of dropping it', () => {
    const { texts, unreadable } = benchmarkClaimTexts(String.raw`{"note": "a\x41"}`)
    assert.deepEqual(texts, [])
    assert.equal(unreadable.length, 1)
    assert.equal(unreadable[0].line, 1)
  })

  it('still reads the claims of an artifact that is not valid JSON', () => {
    // The schema belongs to `validate_published_data.py`; this reader's job is that a
    // syntax error does not stop it before the sentence a reader would see.
    const { texts } = benchmarkClaimTexts('{"a": 1,, "note": "production-ready"}')
    assert.deepEqual(texts, [{ line: 1, text: 'production-ready' }])
  })
})

describe('the reader each root gets', () => {
  it('reads a component whole, so a template line and a script string are both text', () => {
    const source = '<template>\n  <p>production-ready</p>\n</template>\n'
    const { texts } = scannedTexts('/anywhere/app/components/Widget.vue', source, '/anywhere')
    assert.deepEqual(texts.map(text => text.line), [1, 2, 3, 4])
    assert.deepEqual(phraseViolations(texts[1].text), ['positive production-readiness claim'])
  })

  it('reads a benchmark artifact as JSON strings, so a key is not scanned', () => {
    const source = '{"required": true}'
    const { texts } = scannedTexts('/anywhere/public/benchmarks/x.json', source, '/anywhere')
    assert.deepEqual(texts, [])
  })
})

describe('a scanned site tree', () => {
  it('finds a claim in a component template and in its script string', async () => {
    const claims = await withSite({
      'app/components/Widget.vue': [
        '<template>',
        '  <p>production-ready</p>',
        '</template>',
        '<script setup lang="ts">',
        "const note = 'enterprise-grade status'",
        '</script>',
      ].join('\n'),
    }, async root => (await scan(root)).claims)
    assert.deepEqual(claims.map(claim => [claim.file, claim.line, claim.label]), [
      ['app/components/Widget.vue', 2, 'positive production-readiness claim'],
      ['app/components/Widget.vue', 5, 'unsupported enterprise-grade claim'],
    ])
  })

  it('finds a claim in a published benchmark artifact, on the line it sits on', async () => {
    const claims = await withSite({
      'public/benchmarks/x.json': [
        '{',
        '  "suite": "gold-set",',
        '  "note": "battle-tested",',
        '}',
      ].join('\n'),
    }, async root => (await scan(root)).claims)
    assert.deepEqual(claims.map(claim => [claim.file, claim.line, claim.label]), [
      ['public/benchmarks/x.json', 3, 'unsupported battle-tested claim'],
    ])
  })

  it('gates a number under app/data and leaves the same line in a component alone', async () => {
    // The numeric rule is scoped to the typed data root, where a result is authored.
    const files = {
      'app/data/rows.ts': "export const note = '42 ms'\n",
      'app/components/Widget.vue': "<script>\nconst note = '42 ms'\n</script>\n",
    }
    const claims = await withSite(files, async root => (await scan(root)).claims)
    assert.deepEqual(claims.map(claim => [claim.file, claim.label]), [
      ['app/data/rows.ts', 'numeric claim without an artifact reference'],
    ])
  })

  it('reports an artifact it cannot read as a failure instead of crashing or skipping', async () => {
    const { unreadable, claims } = await withSite({
      'public/benchmarks/bad.json': String.raw`{"note": "a\x41"}`,
    }, root => scan(root))
    assert.deepEqual(claims, [])
    assert.equal(unreadable.length, 1)
    assert.equal(unreadable[0].file, 'public/benchmarks/bad.json')
    assert.equal(unreadable[0].label, unreadableLabel)
  })

  it('reports nothing for a tree whose only claim is a denial', async () => {
    // Every docs page is written this way, so a scan that read a denied phrase as a
    // claim would fail the whole tree.
    const result = await withSite({
      'app/components/Widget.vue': '<template>\n  <p>Not production-ready; local evidence only.</p>\n</template>\n',
    }, root => scan(root))
    assert.deepEqual(result, { unreadable: [], claims: [] })
  })
})
