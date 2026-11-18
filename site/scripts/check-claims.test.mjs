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

/**
 * The fixture most cases need: one component, `app/components/Widget.vue`, holding
 * `source` exactly as written. A case about the shape of the file writes the file.
 */
const component = source => ({ 'app/components/Widget.vue': source })

/**
 * The same component with its `<template>` block written for it, one entry of `body`
 * per line. Every case but the ones about the block's own spelling varies only in what
 * the template holds, so the block itself is the fixture's, not the case's.
 */
const template = (...body) => component(`<template>\n${body.join('\n')}\n</template>\n`)

/**
 * What `scan` reports for the throwaway tree holding `files`. Every case below is this
 * call plus its own expectation, so a case reads as the tree it writes and the verdict
 * it demands.
 */
const verdict = files => withSite(files, root => scan(root))

/** A claim as `[line, label]`: the row a single-component case expects back. */
const lineOf = claim => [claim.line, claim.label]

/** A claim as `[file, line, label]`, for a case whose expectation names the file. */
const fileOf = claim => [claim.file, claim.line, claim.label]

/**
 * The claims `scan` reports for `files`, each read as `row` reads it: the line and
 * label a single-component case asserts on, or the file too when the tree holds more
 * than one.
 */
async function claimRows(files, row = lineOf) {
  const { claims } = await verdict(files)
  return claims.map(row)
}

/**
 * The one unreadable finding of the scan of `files`, plus the claims reported beside
 * it. A case about a file the checker cannot read asserts on the finding's file,
 * label, and reason; it cannot use `claimRows`, because both halves are one scan.
 */
async function onlyUnreadable(files) {
  const { unreadable, claims } = await verdict(files)
  assert.equal(unreadable.length, 1)
  return { found: unreadable[0], claims: claims.map(lineOf) }
}

/**
 * The verdict demanded of a tree that must be reported clean: no claim, and nothing
 * the checker could not read.
 */
async function assertNothingReported(files) {
  assert.deepEqual(await verdict(files), { unreadable: [], claims: [] })
}

/**
 * Two elements and then two script strings, each holding one half of one phrase.
 * Nothing a reader sees joins either pair, so no case may report a claim from it: the
 * node reader is asked not to join the elements (`scannedTexts`), and the scan is
 * asked not to join the script strings.
 */
const splitAcrossNodes = [
  '<template>',
  '  <p>guaranteed</p>',
  '  <p>uptime</p>',
  '</template>',
  '<script setup lang="ts">',
  "const a = 'guaranteed'",
  "const b = 'uptime'",
  '</script>',
]

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

/**
 * One component source, read at the path a component of the site is read at, so a
 * case states the source and nothing else.
 */
const componentTexts = source => scannedTexts('/anywhere/app/components/Widget.vue', source, '/anywhere')

describe('the reader each root gets', () => {
  it('reads a component whole, so a template line and a script string are both text', () => {
    const { texts } = componentTexts('<template>\n  <p>production-ready</p>\n</template>\n')
    assert.deepEqual(texts.filter(text => text.occurrences === undefined).map(text => text.line), [1, 2, 3, 4])
    const line = texts.find(text => text.line === 2 && text.occurrences === undefined)
    assert.deepEqual(phraseViolations(line.text), ['positive production-readiness claim'])
  })

  it('reads a template text node whole, with the line its text starts on', () => {
    // A phrase the author broke over two lines renders as one phrase, so the node
    // is scanned as one text with its whitespace collapsed the way a browser
    // collapses it. One line at a time the phrase is never contiguous.
    const { texts } = componentTexts('<template>\n  <p>guaranteed\n    uptime</p>\n</template>\n')
    assert.deepEqual(texts.find(text => text.occurrences !== undefined), {
      line: 2,
      text: 'guaranteed uptime',
      occurrences: [{ label: 'guarantee claim', line: 2 }],
    })
  })

  it('joins no two elements and no script strings into one text', () => {
    // A tag separates two text nodes, so joining across one would invent a phrase
    // nobody wrote: a reader sees `guaranteed` and `uptime` as separate text.
    const { texts } = componentTexts(splitAcrossNodes.join('\n'))
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
const scannedNodeTexts = source => componentTexts(source)
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
    assert.deepEqual(
      await claimRows(template(
        '  <div v-if="x > 1" data-note="\'</template>\'">',
        "    {{ '</template>' }}",
        '    <template #slot></template>',
        '    <p>guaranteed uptime</p>',
        '  </div>',
      )),
      [[5, 'guarantee claim']],
    )
  })

  it('reads a self-closing template and an empty one as elements', async () => {
    // Both are elements, not block openers: counting them as openers left the depth
    // wrong for the rest of the file, so a later `</template>` closed a block that was
    // never open.
    assert.deepEqual(
      await claimRows(template(
        '  <template v-if="a" />',
        '  <template></template>',
        '  <p>production-ready</p>',
      )),
      [[4, 'positive production-readiness claim']],
    )
  })

  it('reads a close tag with whitespace before its `>`', async () => {
    // The block still closes, so the file parses: an unclosed block would be reported
    // as unreadable and the claim in it would not be read at all.
    const found = await verdict(component('<template>\n  <p>production-ready</p>\n</template >'))
    assert.deepEqual(found.unreadable, [])
    assert.deepEqual(found.claims.map(lineOf), [[2, 'positive production-readiness claim']])
  })

  it('reads a generated template of thousands of elements once', async () => {
    // A generated SVG has thousands of elements, each with attributes. The line reader
    // shares one range list with its file instead of copying a line's list per run, so
    // the work stays proportional to the file: 2000 elements, one claim, on its line.
    const elements = Array.from({ length: 2000 }, () => '  <g :data-id="\'g\'"><text>measured</text></g>')
    assert.deepEqual(
      await claimRows(template(...elements, '  <p>production-ready</p>')),
      [[2002, 'positive production-readiness claim']],
    )
  })

  it('reports a component it cannot parse as unreadable', async () => {
    // A template this checker cannot parse is a template whose prose it cannot claim to
    // have read, so the file is a finding rather than silently prose-free. The raw-line
    // reader still reads the file's lines — it does not depend on the parse, and a
    // phrase spelled on one line is one a reader would see — but the failure is the
    // finding that stops the check.
    const { found, claims } = await onlyUnreadable(component('<template>\n  <p>guaranteed uptime</p>\n'))
    assert.equal(found.file, 'app/components/Widget.vue')
    assert.equal(found.label, unreadableLabel)
    assert.match(found.text, /does not parse/)
    assert.deepEqual(claims, [[2, 'guarantee claim']])
  })

  it('reports a template in another language as unreadable instead of parsing it as HTML', async () => {
    // An HTML parse of a pug template is invented prose. The file renders text this
    // checker cannot read, which is a finding, not a skip.
    const { found, claims } = await onlyUnreadable(component('<template lang="pug">\np Measured\n</template>\n'))
    assert.deepEqual(claims, [])
    assert.equal(found.label, unreadableLabel)
    assert.match(found.text, /pug/)
  })

  it('keeps the whitespace of a pre, so a line break there is not a phrase', async () => {
    // Vue preserves whitespace inside `<pre>`, so a reader sees two lines and the page
    // never states the phrase. Condensing it there would invent a claim the same words
    // in a paragraph do state.
    assert.deepEqual(
      await claimRows(template(
        '  <pre>production',
        '  ready</pre>',
        '  <p>production',
        '  ready</p>',
      )),
      [[4, 'positive production-readiness claim']],
    )
  })

  it('reports a node it cannot map exactly at the line the node starts on', async () => {
    // `&mdash;` renders a character this reader does not decode, so the offset map from
    // the node's text back to the source is not recoverable. The claim is still
    // reported, at the line the node starts on — the most the compiler can vouch for —
    // rather than missed, or given a column that is not its own.
    assert.deepEqual(
      await claimRows(template(
        '  <p>',
        '    measured &mdash; still',
        '    guaranteed uptime</p>',
      )),
      [[2, 'guarantee claim']],
    )
  })

  it('reports a template that lives in another file as unreadable', async () => {
    // `<template src="…">` renders text held in a file this scan does not read, so the
    // component is unreadable rather than empty.
    const { found, claims } = await onlyUnreadable(component('<template src="./Widget.html"></template>\n'))
    assert.deepEqual(claims, [])
    assert.match(found.text, /no inline AST/)
  })

  it('reports nothing for a phrase an attribute value holds on one line', async () => {
    // A value is markup, not prose: the paragraph renders `Measured` and nothing else.
    await assertNothingReported(template('  <p data-note="production-ready">Measured</p>'))
  })

  it('reports nothing for a phrase a comment holds', async () => {
    // A comment renders nothing, so a claim in one is not a claim the page makes.
    await assertNothingReported(template('  <!-- production-ready -->', '  <p>Measured</p>'))
  })
})

/**
 * Which props the raw-line reader leaves alone. The default is to scan: a prop value
 * that reaches a reader is prose, and a false positive on one is visible in review
 * while a missed claim is not. Only the values a browser cannot render as text are
 * quiet.
 */
describe('a prop and the reader', () => {
  it('reports a phrase a component prop carries, because the child may render it', async () => {
    // `BenchmarkSectionHeader` renders its `title`. Suppressing every prop made this
    // phrase invisible, so editing this value escaped the check: a prop is scanned
    // unless its name is one that cannot render.
    assert.deepEqual(
      await claimRows(template('  <BenchmarkSectionHeader title="guaranteed uptime" />')),
      [[2, 'guarantee claim']],
    )
  })

  it('reports a phrase v-text assigns, because the directive writes the text', async () => {
    // Vue assigns the directive value to `textContent`, so the element has no text
    // node for the node reader to see: the value is the only rendered text there is.
    assert.deepEqual(
      await claimRows(template('  <p v-text="\'guaranteed uptime\'"></p>')),
      [[2, 'guarantee claim']],
    )
  })

  it('reports a phrase v-html assigns, scanned as the text of the markup it renders', async () => {
    // The value is markup: the tags in it are not text, but the words between them
    // are. Scanning the whole value over-reports a tag name and never misses prose,
    // which is the direction this checker fails in.
    assert.deepEqual(
      await claimRows(template('  <p v-html="\'<b>guaranteed uptime</b>\'"></p>')),
      [[2, 'guarantee claim']],
    )
  })

  it('reports a phrase a title attribute carries, static and bound', async () => {
    // A browser shows a title as a tooltip, so its text reaches a reader. The bound
    // form sets the same attribute from an expression and is read the same way.
    assert.deepEqual(
      await claimRows(template(
        '  <p title="production-ready">Measured</p>',
        '  <p :title="\'battle-tested\'">Measured</p>',
        '  <img alt="enterprise-grade" src="/x.png">',
      )),
      [
        [2, 'positive production-readiness claim'],
        [3, 'unsupported battle-tested claim'],
        [4, 'unsupported enterprise-grade claim'],
      ],
    )
  })

  it('reports nothing for a data-* value, including the one this rule was written for', async () => {
    // The original finding: a `data-*` value is read by scripts and CSS selectors and
    // rendered by nothing, so a phrase inside one is not a claim the page makes — even
    // when it spells a tag-ending `>`.
    await assertNothingReported(template('  <p data-note="see > guaranteed uptime">Measured</p>'))
  })

  it('reports a phrase an aria-label speaks, and nothing for an attribute only a script reads', async () => {
    // Most `aria-*` attributes are machine metadata — `aria-hidden` names a condition —
    // but `aria-label` is prose a screen reader speaks to the reader, so a prohibited
    // phrase in one is a claim the page makes to a user who never sees the paragraph.
    // Treating every `aria-*` as non-rendering missed it.
    assert.deepEqual(
      await claimRows(template(
        '  <p aria-label="guaranteed uptime">Measured</p>',
        '  <p :aria-label="\'battle-tested\'">Measured</p>',
        '  <p aria-hidden="production-ready">Measured</p>',
      )),
      [
        [2, 'guarantee claim'],
        [3, 'unsupported battle-tested claim'],
      ],
    )
  })

  it('reports nothing for a prop that cannot render text, bound or directive', async () => {
    // A class, a style, an id, an ARIA token, an event handler, a two-way binding and
    // the presence and visibility directives all put their value somewhere other than
    // the text a browser shows.
    await assertNothingReported(template(
      '  <div',
      '    :class="\'production-ready\'"',
      '    :style="\'battle-tested\'"',
      '    :data-note="\'guaranteed uptime\'"',
      '    role="five nines"',
      '    @click="\'enterprise-grade\'"',
      '    v-on:keyup.enter="\'production-ready\'"',
      '    v-model="\'battle-tested\'"',
      '    v-show="\'guaranteed uptime\'"',
      '    v-if="\'five nines\'"',
      '  >Measured</div>',
    ))
  })

  it('decides each prop on its own, so a quiet one does not excuse its neighbour', async () => {
    // The reader drops one range per non-rendering prop. A `data-*` beside a `title`
    // must silence only its own value, and the finding must still be reported once,
    // at the line the tag sits on.
    const tag = '  <div class="note" data-note="guaranteed uptime" title="production-ready">Measured</div>'
    assert.deepEqual(await claimRows(template(tag)), [[2, 'positive production-readiness claim']])
  })

  it('reads a directive the parser left unparsed as a name no browser renders', async () => {
    // `<div v-pre @click="'production-ready'">` hands the parser a plain attribute
    // literally named `@click`, because `v-pre` stops compilation. That attribute sets
    // no text either way, so the phrase inside it is not prose.
    await assertNothingReported(template(
      '  <div v-pre @click="\'production-ready\'" :class="\'battle-tested\'">Measured</div>',
    ))
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
    assert.deepEqual(
      await claimRows(component([
        '<template>',
        '  <p>production-ready</p>',
        '</template>',
        '<script setup lang="ts">',
        "const note = 'enterprise-grade status'",
        '</script>',
      ].join('\n')), fileOf),
      [
        ['app/components/Widget.vue', 2, 'positive production-readiness claim'],
        ['app/components/Widget.vue', 5, 'unsupported enterprise-grade claim'],
      ],
    )
  })

  it('finds a claim a template text node breaks over two lines, on the line it starts', async () => {
    // The node renders "guaranteed uptime", so the split claim is one claim. The
    // line reader sees two fragments and reports neither, and the node reader points
    // at the line the phrase starts on rather than at the tag that opens the node.
    assert.deepEqual(
      await claimRows(template('  <p>', '    guaranteed', '    uptime</p>'), fileOf),
      [['app/components/Widget.vue', 3, 'guarantee claim']],
    )
  })

  it('reports a claim inside one line of a two-line node once, not twice', async () => {
    // The node is read whole and the line reader leaves the node's characters to it,
    // so an occurrence that sits inside one line of a two-line node is reported once.
    assert.deepEqual(
      await claimRows(template('  <p>production-ready', '    and measured</p>')),
      [[2, 'positive production-readiness claim']],
    )
  })

  it('reports a cross-line claim on the line its phrase starts, not the node first line', async () => {
    // The node's text starts on line 3, the phrase on line 4. Reading the node whole
    // and reporting it at its first line would point at the wrong line.
    assert.deepEqual(
      await claimRows(template('  <p>', '    measured', '    guaranteed', '    uptime</p>')),
      [[4, 'guarantee claim']],
    )
  })

  it('reports nothing for a phrase a quoted attribute value holds', async () => {
    // The tag ends at the `>` outside the value, so the value is not text a reader
    // sees. Ending the tag at the `>` inside it would read `guaranteed uptime` as
    // rendered prose and report a claim the paragraph does not display.
    await assertNothingReported(template('  <p data-note="see > guaranteed', '    uptime">Measured</p>'))
  })

  it('ends the template block at its own close, not at one a script spells', async () => {
    // The file's last `</template>` sits inside a script string. Reading to it would
    // make the script a text node, and a script comment that splits a phrase over two
    // lines would then report a claim the page never renders.
    await assertNothingReported(component([
      '<template>',
      '  <p>Measured</p>',
      '</template>',
      '<script setup lang="ts">',
      '/* guaranteed',
      '   uptime */',
      "const closing = '</template>'",
      '</script>',
    ].join('\n')))
  })

  it('decodes a character reference, at the source line of the phrase it spells', async () => {
    // `&#32;` and `&nbsp;` render as spaces, so the node states the phrases even
    // though the source spells none of them. The reference on line 3 shifts every
    // decoded offset after it, and the source map still points at the line the phrase
    // starts on.
    assert.deepEqual(
      await claimRows(template(
        '  <p>',
        '    measured as&#32;0 ms,',
        '    guaranteed&#32;uptime</p>',
        '  <p>guaranteed&nbsp;uptime</p>',
      )),
      [
        [4, 'guarantee claim'],
        [5, 'guarantee claim'],
      ],
    )
  })

  it('normalises whitespace inside one source line, so a collapsed run is a phrase', async () => {
    // Vue collapses the run, so the paragraph renders `production ready`; the raw line
    // keeps three spaces and the single-line node was not read at all before.
    assert.deepEqual(
      await claimRows(template('  <p>production   ready</p>')),
      [[2, 'positive production-readiness claim']],
    )
  })

  it('decides a denial against the whole clause, not the line the claim sits on', async () => {
    // `We do not offer` is on the line before the claim. One line at a time the denial
    // is invisible and the raw-line pass reports a claim the node denies.
    await assertNothingReported(template('  <p>', '    We do not offer', '    production-ready service.</p>'))
  })

  it('still reports an occurrence in a clause the denial does not cover', async () => {
    // The semicolon ends the denied clause, so the claim after it is a claim the page
    // states, and the scan must not excuse it with the denial before the break.
    assert.deepEqual(
      await claimRows(template('  <p>', '    We do not offer', '    support; production-ready service.</p>')),
      [[4, 'positive production-readiness claim']],
    )
  })

  it('puts every finding on its own line in a component with many nodes', async () => {
    // Each node resolves its line from the indexed line starts rather than by
    // rescanning the file from its start, and the line it reports is its own.
    const body = []
    for (let index = 0; index < 50; index += 1) body.push('  <p>Measured</p>', '  <p>production-ready</p>')
    assert.deepEqual(
      await claimRows(template(...body), claim => claim.line),
      Array.from({ length: 50 }, (_, index) => 3 + index * 2),
    )
  })

  it('orders findings by the line they report, not by the rule that found them', async () => {
    // One node states both phrases, and the rule for `production-ready` runs before the
    // rule for `guaranteed uptime`, so the node's occurrence list is rule-ordered. The
    // claim on line 4 must still be reported before the one on line 7.
    assert.deepEqual(
      await claimRows(template(
        '  <p>',
        '    measured',
        '    guaranteed uptime',
        '    and',
        '    also',
        '    production-ready',
        '  </p>',
      )),
      [
        [4, 'guarantee claim'],
        [7, 'positive production-readiness claim'],
      ],
    )
  })

  it('reports nothing for a phrase no single text node states', async () => {
    // `guaranteed` and `uptime` sit in two elements and then in two script strings.
    // Neither pair renders as one sentence, so neither is a claim.
    await assertNothingReported(component(splitAcrossNodes.join('\n')))
  })

  it('finds a claim in a published benchmark artifact, on the line it sits on', async () => {
    assert.deepEqual(
      await claimRows({
        'public/benchmarks/x.json': [
          '{',
          '  "suite": "gold-set",',
          '  "note": "battle-tested",',
          '}',
        ].join('\n'),
      }, fileOf),
      [['public/benchmarks/x.json', 3, 'unsupported battle-tested claim']],
    )
  })

  it('gates a number under app/data and leaves the same line in a component alone', async () => {
    // The numeric rule is scoped to the typed data root, where a result is authored.
    assert.deepEqual(
      await claimRows({
        'app/data/rows.ts': "export const note = '42 ms'\n",
        'app/components/Widget.vue': "<script>\nconst note = '42 ms'\n</script>\n",
      }, fileOf),
      [['app/data/rows.ts', 1, 'numeric claim without an artifact reference']],
    )
  })

  it('reports an artifact it cannot read as a failure instead of crashing or skipping', async () => {
    const { found, claims } = await onlyUnreadable({ 'public/benchmarks/bad.json': String.raw`{"note": "a\x41"}` })
    assert.deepEqual(claims, [])
    assert.equal(found.file, 'public/benchmarks/bad.json')
    assert.equal(found.label, unreadableLabel)
  })

  it('reports nothing for a tree whose only claim is a denial', async () => {
    // Every docs page is written this way, so a scan that read a denied phrase as a
    // claim would fail the whole tree.
    await assertNothingReported(template('  <p>Not production-ready; local evidence only.</p>'))
  })
})
