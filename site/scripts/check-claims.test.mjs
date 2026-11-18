import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { mkdir, mkdtemp, readdir, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  benchmarkClaimTexts,
  phraseViolations,
  readJsonString,
  scan,
  scannedTexts,
  unreadableLabel,
} from './check-claims.mjs'

// The compiler is the reference for what a template renders, so the reader's own
// decoding is compared against it here rather than against a second pattern.
import { parse } from '@vue/compiler-sfc'

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
    assert.deepEqual(texts.filter(text => text.occurrences === undefined).map(text => text.line), [1, 2, 3, 4])
    const line = texts.find(text => text.line === 2 && text.occurrences === undefined)
    assert.deepEqual(phraseViolations(line.text), ['positive production-readiness claim'])
  })

  it('reads a template text node whole, with the line its text starts on', () => {
    // A phrase the author broke over two lines renders as one phrase, so the node
    // is scanned as one text with its whitespace collapsed the way a browser
    // collapses it. One line at a time the phrase is never contiguous.
    const source = '<template>\n  <p>guaranteed\n    uptime</p>\n</template>\n'
    const { texts } = scannedTexts('/anywhere/app/components/Widget.vue', source, '/anywhere')
    assert.deepEqual(texts.find(text => text.occurrences !== undefined), {
      line: 2,
      text: 'guaranteed uptime',
      occurrences: [{ label: 'guarantee claim', line: 2 }],
    })
  })

  it('joins no two elements and no script strings into one text', () => {
    // A tag separates two text nodes, so joining across one would invent a phrase
    // nobody wrote: a reader sees `guaranteed` and `uptime` as separate text.
    const source = [
      '<template>',
      '  <p>guaranteed</p>',
      '  <p>uptime</p>',
      '</template>',
      '<script setup lang="ts">',
      "const a = 'guaranteed'",
      "const b = 'uptime'",
      '</script>',
    ].join('\n')
    const { texts } = scannedTexts('/anywhere/app/components/Widget.vue', source, '/anywhere')
    assert.deepEqual(texts.filter(text => text.occurrences !== undefined).map(text => text.text), [
      'guaranteed',
      'uptime',
    ])
  })

  it('reads a benchmark artifact as JSON strings, so a key is not scanned', () => {
    const source = '{"required": true}'
    const { texts } = scannedTexts('/anywhere/public/benchmarks/x.json', source, '/anywhere')
    assert.deepEqual(texts, [])
  })
})

/**
 * Every single-file component under `site/app`: the input the claim scan reads in
 * this repository, so the reader is pinned on real bodies and not only on constructed
 * ones.
 */
async function siteComponentSources() {
  const app = fileURLToPath(new URL('../app/', import.meta.url))
  const files = (await readdir(app, { recursive: true })).filter(name => name.endsWith('.vue'))
  return Promise.all(files.map(name => readFile(join(app, name), 'utf8')))
}

/**
 * The rendered text of every text node the compiler finds in `source`, flattened so a
 * leading or trailing space is not read as a disagreement between two decoders.
 */
function compilerTexts(source) {
  const { descriptor, errors } = parse(source, { filename: 'Component.vue' })
  if (errors.length > 0) throw new Error(errors[0].message)
  const texts = []
  const walk = node => {
    if (node.type === 2) texts.push(node.content.replace(/\s+/g, ' ').trim())
    for (const child of node.children ?? []) walk(child)
  }
  walk(descriptor.template.ast)
  return texts.filter(text => text !== '')
}

/**
 * The same list as the scan reads it: the text of every template text node, flattened
 * the same way.
 */
const scannedNodeTexts = source => scannedTexts('/anywhere/app/components/Widget.vue', source, '/anywhere')
  .texts.filter(text => text.occurrences !== undefined)
  .map(text => text.text.replace(/\s+/g, ' ').trim())

describe('the template the compiler parses', () => {
  it('reads every component in the site the way the compiler renders it', async () => {
    // The reader decodes the node's own source range to keep a source map for the
    // lines it reports; this pins that its decoding is Vue's, on every real body.
    const sources = await siteComponentSources()
    assert.ok(sources.length > 0)
    for (const source of sources) assert.deepEqual(scannedNodeTexts(source), compilerTexts(source))
  })

  it('closes the block where the compiler does, whatever an attribute or an interpolation spells', async () => {
    // `</template>` spelled in an attribute value, in an interpolation, and in a slot
    // name is text to a scanner and none of them to the compiler. Ending the block at
    // the first one it saw made the rest of the file prose.
    const claims = await withSite({
      'app/components/Widget.vue': [
        '<template>',
        '  <div v-if="x > 1" data-note="\'</template>\'">',
        "    {{ '</template>' }}",
        '    <template #slot></template>',
        '    <p>guaranteed uptime</p>',
        '  </div>',
        '</template>',
      ].join('\n'),
    }, async root => (await scan(root)).claims)
    assert.deepEqual(claims.map(claim => [claim.line, claim.label]), [[5, 'guarantee claim']])
  })

  it('reads a self-closing template and an empty one as elements', async () => {
    // Both are elements, not block openers: counting them as openers left the depth
    // wrong for the rest of the file, so a later `</template>` closed a block that was
    // never open.
    const claims = await withSite({
      'app/components/Widget.vue': [
        '<template>',
        '  <template v-if="a" />',
        '  <template></template>',
        '  <p>production-ready</p>',
        '</template>',
      ].join('\n'),
    }, async root => (await scan(root)).claims)
    assert.deepEqual(claims.map(claim => [claim.line, claim.label]), [[4, 'positive production-readiness claim']])
  })

  it('reads a close tag with whitespace before its `>`', async () => {
    // The block still closes, so the file parses: an unclosed block would be reported
    // as unreadable and the claim in it would not be read at all.
    const { unreadable, claims } = await withSite({
      'app/components/Widget.vue': [
        '<template>',
        '  <p>production-ready</p>',
        '</template >',
      ].join('\n'),
    }, root => scan(root))
    assert.deepEqual(unreadable, [])
    assert.deepEqual(claims.map(claim => [claim.line, claim.label]), [[2, 'positive production-readiness claim']])
  })

  it('reads a generated template of thousands of elements once', async () => {
    // A generated SVG has thousands of elements, each with attributes. The line reader
    // shares one range list with its file instead of copying a line's list per run, so
    // the work stays proportional to the file: 2000 elements, one claim, on its line.
    const lines = ['<template>']
    for (let index = 0; index < 2000; index += 1) lines.push('  <g :data-id="\'g\'"><text>measured</text></g>')
    lines.push('  <p>production-ready</p>', '</template>')
    const claims = await withSite({ 'app/components/Widget.vue': lines.join('\n') },
      async root => (await scan(root)).claims)
    assert.deepEqual(claims.map(claim => [claim.line, claim.label]), [[2002, 'positive production-readiness claim']])
  })

  it('reports a component it cannot parse as unreadable', async () => {
    // A template this checker cannot parse is a template whose prose it cannot claim to
    // have read, so the file is a finding rather than silently prose-free. The raw-line
    // reader still reads the file's lines — it does not depend on the parse, and a
    // phrase spelled on one line is one a reader would see — but the failure is the
    // finding that stops the check.
    const { unreadable, claims } = await withSite({
      'app/components/Widget.vue': '<template>\n  <p>guaranteed uptime</p>\n',
    }, root => scan(root))
    assert.equal(unreadable.length, 1)
    assert.equal(unreadable[0].file, 'app/components/Widget.vue')
    assert.equal(unreadable[0].label, unreadableLabel)
    assert.match(unreadable[0].text, /does not parse/)
    assert.deepEqual(claims.map(claim => [claim.line, claim.label]), [[2, 'guarantee claim']])
  })

  it('reports a template in another language as unreadable instead of parsing it as HTML', async () => {
    // An HTML parse of a pug template is invented prose. The file renders text this
    // checker cannot read, which is a finding, not a skip.
    const { unreadable, claims } = await withSite({
      'app/components/Widget.vue': '<template lang="pug">\np Measured\n</template>\n',
    }, root => scan(root))
    assert.deepEqual(claims, [])
    assert.equal(unreadable.length, 1)
    assert.equal(unreadable[0].label, unreadableLabel)
    assert.match(unreadable[0].text, /pug/)
  })

  it('keeps the whitespace of a pre, so a line break there is not a phrase', async () => {
    // Vue preserves whitespace inside `<pre>`, so a reader sees two lines and the page
    // never states the phrase. Condensing it there would invent a claim the same words
    // in a paragraph do state.
    const claims = await withSite({
      'app/components/Widget.vue': [
        '<template>',
        '  <pre>production',
        '  ready</pre>',
        '  <p>production',
        '  ready</p>',
        '</template>',
      ].join('\n'),
    }, async root => (await scan(root)).claims)
    assert.deepEqual(claims.map(claim => [claim.line, claim.label]), [[4, 'positive production-readiness claim']])
  })

  it('reports a node it cannot map exactly at the line the node starts on', async () => {
    // `&mdash;` renders a character this reader does not decode, so the offset map from
    // the node's text back to the source is not recoverable. The claim is still
    // reported, at the line the node starts on — the most the compiler can vouch for —
    // rather than missed, or given a column that is not its own.
    const claims = await withSite({
      'app/components/Widget.vue': [
        '<template>',
        '  <p>',
        '    measured &mdash; still',
        '    guaranteed uptime</p>',
        '</template>',
      ].join('\n'),
    }, async root => (await scan(root)).claims)
    assert.deepEqual(claims.map(claim => [claim.line, claim.label]), [[2, 'guarantee claim']])
  })

  it('reports a template that lives in another file as unreadable', async () => {
    // `<template src="…">` renders text held in a file this scan does not read, so the
    // component is unreadable rather than empty.
    const { unreadable, claims } = await withSite({
      'app/components/Widget.vue': '<template src="./Widget.html"></template>\n',
    }, root => scan(root))
    assert.deepEqual(claims, [])
    assert.equal(unreadable.length, 1)
    assert.match(unreadable[0].text, /no inline AST/)
  })

  it('reports nothing for a phrase an attribute value holds on one line', async () => {
    // A value is markup, not prose: the paragraph renders `Measured` and nothing else.
    const result = await withSite({
      'app/components/Widget.vue': [
        '<template>',
        '  <p data-note="production-ready">Measured</p>',
        '</template>',
      ].join('\n'),
    }, root => scan(root))
    assert.deepEqual(result, { unreadable: [], claims: [] })
  })

  it('reports nothing for a phrase a comment holds', async () => {
    // A comment renders nothing, so a claim in one is not a claim the page makes.
    const result = await withSite({
      'app/components/Widget.vue': [
        '<template>',
        '  <!-- production-ready -->',
        '  <p>Measured</p>',
        '</template>',
      ].join('\n'),
    }, root => scan(root))
    assert.deepEqual(result, { unreadable: [], claims: [] })
  })
})

describe('the clause a denial covers', () => {
  it('scopes a denial to its own clause in a text with many breaks', () => {
    // The clause boundaries are found once per text and read by binary search; this
    // pins that the lookup draws the same boundaries the linear scan did: the denial
    // reaches `battle-tested`, the comma ends its claim, and the last clause is not
    // denied at all.
    assert.deepEqual(
      phraseViolations('not audited, enterprise-grade; not battle-tested; production-ready'),
      ['positive production-readiness claim', 'unsupported enterprise-grade claim'],
    )
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

  it('finds a claim a template text node breaks over two lines, on the line it starts', async () => {
    // The node renders "guaranteed uptime", so the split claim is one claim. The
    // line reader sees two fragments and reports neither, and the node reader points
    // at the line the phrase starts on rather than at the tag that opens the node.
    const claims = await withSite({
      'app/components/Widget.vue': [
        '<template>',
        '  <p>',
        '    guaranteed',
        '    uptime</p>',
        '</template>',
      ].join('\n'),
    }, async root => (await scan(root)).claims)
    assert.deepEqual(claims.map(claim => [claim.file, claim.line, claim.label]), [
      ['app/components/Widget.vue', 3, 'guarantee claim'],
    ])
  })

  it('reports a claim inside one line of a two-line node once, not twice', async () => {
    // The node is read whole and the line reader leaves the node's characters to it,
    // so an occurrence that sits inside one line of a two-line node is reported once.
    const claims = await withSite({
      'app/components/Widget.vue': [
        '<template>',
        '  <p>production-ready',
        '    and measured</p>',
        '</template>',
      ].join('\n'),
    }, async root => (await scan(root)).claims)
    assert.deepEqual(claims.map(claim => [claim.line, claim.label]), [
      [2, 'positive production-readiness claim'],
    ])
  })

  it('reports a cross-line claim on the line its phrase starts, not the node first line', async () => {
    // The node's text starts on line 3, the phrase on line 4. Reading the node whole
    // and reporting it at its first line would point at the wrong line.
    const claims = await withSite({
      'app/components/Widget.vue': [
        '<template>',
        '  <p>',
        '    measured',
        '    guaranteed',
        '    uptime</p>',
        '</template>',
      ].join('\n'),
    }, async root => (await scan(root)).claims)
    assert.deepEqual(claims.map(claim => [claim.line, claim.label]), [[4, 'guarantee claim']])
  })

  it('reports nothing for a phrase a quoted attribute value holds', async () => {
    // The tag ends at the `>` outside the value, so the value is not text a reader
    // sees. Ending the tag at the `>` inside it would read `guaranteed uptime` as
    // rendered prose and report a claim the paragraph does not display.
    const result = await withSite({
      'app/components/Widget.vue': [
        '<template>',
        '  <p data-note="see > guaranteed',
        '    uptime">Measured</p>',
        '</template>',
      ].join('\n'),
    }, root => scan(root))
    assert.deepEqual(result, { unreadable: [], claims: [] })
  })

  it('ends the template block at its own close, not at one a script spells', async () => {
    // The file's last `</template>` sits inside a script string. Reading to it would
    // make the script a text node, and a script comment that splits a phrase over two
    // lines would then report a claim the page never renders.
    const result = await withSite({
      'app/components/Widget.vue': [
        '<template>',
        '  <p>Measured</p>',
        '</template>',
        '<script setup lang="ts">',
        '/* guaranteed',
        '   uptime */',
        "const closing = '</template>'",
        '</script>',
      ].join('\n'),
    }, root => scan(root))
    assert.deepEqual(result, { unreadable: [], claims: [] })
  })

  it('decodes a character reference, at the source line of the phrase it spells', async () => {
    // `&#32;` and `&nbsp;` render as spaces, so the node states the phrases even
    // though the source spells none of them. The reference on line 3 shifts every
    // decoded offset after it, and the source map still points at the line the phrase
    // starts on.
    const claims = await withSite({
      'app/components/Widget.vue': [
        '<template>',
        '  <p>',
        '    measured as&#32;0 ms,',
        '    guaranteed&#32;uptime</p>',
        '  <p>guaranteed&nbsp;uptime</p>',
        '</template>',
      ].join('\n'),
    }, async root => (await scan(root)).claims)
    assert.deepEqual(claims.map(claim => [claim.line, claim.label]), [
      [4, 'guarantee claim'],
      [5, 'guarantee claim'],
    ])
  })

  it('normalises whitespace inside one source line, so a collapsed run is a phrase', async () => {
    // Vue collapses the run, so the paragraph renders `production ready`; the raw line
    // keeps three spaces and the single-line node was not read at all before.
    const claims = await withSite({
      'app/components/Widget.vue': '<template>\n  <p>production   ready</p>\n</template>\n',
    }, async root => (await scan(root)).claims)
    assert.deepEqual(claims.map(claim => [claim.line, claim.label]), [
      [2, 'positive production-readiness claim'],
    ])
  })

  it('decides a denial against the whole clause, not the line the claim sits on', async () => {
    // `We do not offer` is on the line before the claim. One line at a time the denial
    // is invisible and the raw-line pass reports a claim the node denies.
    const result = await withSite({
      'app/components/Widget.vue': [
        '<template>',
        '  <p>',
        '    We do not offer',
        '    production-ready service.</p>',
        '</template>',
      ].join('\n'),
    }, root => scan(root))
    assert.deepEqual(result, { unreadable: [], claims: [] })
  })

  it('still reports an occurrence in a clause the denial does not cover', async () => {
    // The semicolon ends the denied clause, so the claim after it is a claim the page
    // states, and the scan must not excuse it with the denial before the break.
    const claims = await withSite({
      'app/components/Widget.vue': [
        '<template>',
        '  <p>',
        '    We do not offer',
        '    support; production-ready service.</p>',
        '</template>',
      ].join('\n'),
    }, async root => (await scan(root)).claims)
    assert.deepEqual(claims.map(claim => [claim.line, claim.label]), [
      [4, 'positive production-readiness claim'],
    ])
  })

  it('puts every finding on its own line in a component with many nodes', async () => {
    // Each node resolves its line from the indexed line starts rather than by
    // rescanning the file from its start, and the line it reports is its own.
    const lines = ['<template>']
    for (let index = 0; index < 50; index += 1) lines.push('  <p>Measured</p>', '  <p>production-ready</p>')
    lines.push('</template>')
    const claims = await withSite({ 'app/components/Widget.vue': lines.join('\n') },
      async root => (await scan(root)).claims)
    assert.deepEqual(claims.map(claim => claim.line), Array.from({ length: 50 }, (_, index) => 3 + index * 2))
  })

  it('orders findings by the line they report, not by the rule that found them', async () => {
    // One node states both phrases, and the rule for `production-ready` runs before the
    // rule for `guaranteed uptime`, so the node's occurrence list is rule-ordered. The
    // claim on line 4 must still be reported before the one on line 7.
    const claims = await withSite({
      'app/components/Widget.vue': [
        '<template>',
        '  <p>',
        '    measured',
        '    guaranteed uptime',
        '    and',
        '    also',
        '    production-ready',
        '  </p>',
        '</template>',
      ].join('\n'),
    }, async root => (await scan(root)).claims)
    assert.deepEqual(claims.map(claim => [claim.line, claim.label]), [
      [4, 'guarantee claim'],
      [7, 'positive production-readiness claim'],
    ])
  })

  it('reports nothing for a phrase no single text node states', async () => {
    // `guaranteed` and `uptime` sit in two elements and then in two script strings.
    // Neither pair renders as one sentence, so neither is a claim.
    const result = await withSite({
      'app/components/Widget.vue': [
        '<template>',
        '  <p>guaranteed</p>',
        '  <p>uptime</p>',
        '</template>',
        '<script setup lang="ts">',
        "const a = 'guaranteed'",
        "const b = 'uptime'",
        '</script>',
      ].join('\n'),
    }, root => scan(root))
    assert.deepEqual(result, { unreadable: [], claims: [] })
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
