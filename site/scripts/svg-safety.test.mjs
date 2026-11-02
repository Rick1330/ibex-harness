import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { assertInertSvg, containsActiveSvgContent } from '../app/utils/svg-safety.ts'

// A representative mermaid output: an svg with an HTML label inside
// foreignObject and inline styles. This is the shape the guard must allow.
const SAFE_SVG = [
  '<svg id="ibex-mermaid-1" width="100%" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 96">',
  '<style>#ibex-mermaid-1 .label{font-family:Geist,sans-serif}</style>',
  '<g class="node" transform="translate(0, 0)">',
  '<foreignObject width="120" height="24"><div xmlns="http://www.w3.org/1999/xhtml">',
  '<span class="nodeLabel">Proxy &amp; context</span>',
  '</div></foreignObject>',
  '</g>',
  '</svg>',
].join('')

describe('rendered diagram safety guard', () => {
  it('accepts the markup mermaid produces in strict mode', () => {
    assert.equal(containsActiveSvgContent(SAFE_SVG), false)
    assert.doesNotThrow(() => assertInertSvg(SAFE_SVG))
    assert.doesNotThrow(() => assertInertSvg(''))
  })

  it('rejects embedding elements', () => {
    for (const tag of ['script', 'iframe', 'object', 'embed']) {
      const svg = `<svg><${tag} src="x"></${tag}></svg>`
      assert.equal(containsActiveSvgContent(svg), true, tag)
      assert.throws(() => assertInertSvg(svg), /refusing to mount/, tag)
    }
  })

  it('rejects inline event handlers', () => {
    for (const attribute of ['onload', 'onclick', 'onerror', 'onbegin']) {
      const svg = `<svg ${attribute}="alert(1)"><g /></svg>`
      assert.equal(containsActiveSvgContent(svg), true, attribute)
      assert.throws(() => assertInertSvg(svg), /refusing to mount/, attribute)
    }
  })

  it('rejects javascript: URLs', () => {
    const svg = '<svg><a href="javascript:alert(1)"><text>go</text></a></svg>'
    assert.equal(containsActiveSvgContent(svg), true)
    assert.throws(() => assertInertSvg(svg), /refusing to mount/)
  })

  it('does not reject attributes that merely start with the letters "on"', () => {
    // `opacity` and a hyphenated `onclick-ignore` are not event handlers: the
    // pattern requires the attribute name to end immediately at `=`.
    for (const attribute of ['opacity="0.5"', 'onclick-ignore="x"']) {
      const svg = `<svg ${attribute}><g /></svg>`
      assert.equal(containsActiveSvgContent(svg), false, attribute)
    }
  })
})
