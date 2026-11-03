import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  buildRss,
  clean,
  isCommitLabel,
  parseChangelog,
  parseReleaseHeading,
  parseTrailingReference,
  stripMarkdownLinks,
} from './build-releases.mjs'

const COMPARE_URL = 'https://github.com/Rick1330/ibex-harness/compare/v0.1.8...v0.1.9'
const ISSUE_URL = 'https://github.com/Rick1330/ibex-harness/issues/911'
const COMMIT_URL = 'https://github.com/Rick1330/ibex-harness/commit/2411f73910e80cd80aefdf22edfab9b8fcde05c5'

describe('stripMarkdownLinks', () => {
  it('replaces a single link with its label', () => {
    assert.equal(stripMarkdownLinks('see [docs](https://example.com) now'), 'see docs now')
  })

  it('replaces multiple links and keeps surrounding text', () => {
    assert.equal(stripMarkdownLinks('[a](u1) and [b](u2)'), 'a and b')
  })

  it('leaves text without links untouched', () => {
    assert.equal(stripMarkdownLinks('plain text'), 'plain text')
  })
})

describe('clean', () => {
  it('strips links, bold markers, and collapses whitespace', () => {
    assert.equal(clean('**bold** [link](https://x)   tail'), 'bold link tail')
  })
})

describe('parseReleaseHeading', () => {
  it('parses version without the bracket, compare URL, and date', () => {
    assert.deepEqual(
      parseReleaseHeading(`## [0.1.9](${COMPARE_URL}) (2026-08-12)`),
      { version: '0.1.9', compareUrl: COMPARE_URL, date: '2026-08-12' },
    )
  })

  it('rejects non-heading lines and malformed dates', () => {
    assert.equal(parseReleaseHeading('### Fixed'), null)
    assert.equal(parseReleaseHeading(`## [0.1.9](${COMPARE_URL}) (next week)`), null)
  })
})

describe('isCommitLabel', () => {
  it('accepts short and full hashes and rejects issue labels', () => {
    assert.equal(isCommitLabel('2411f73'), true)
    assert.equal(isCommitLabel('a'.repeat(40)), true)
    assert.equal(isCommitLabel('#911'), false)
    assert.equal(isCommitLabel('release'), false)
  })
})

describe('parseTrailingReference', () => {
  it('extracts a trailing issue reference', () => {
    const { text, refs } = parseTrailingReference(`certify provenance contract ([#911](${ISSUE_URL}))`)
    assert.equal(text, 'certify provenance contract')
    assert.deepEqual(refs.issue, { number: '911', url: ISSUE_URL })
    assert.equal(refs.commit, null)
  })

  it('extracts a trailing commit reference', () => {
    const { text, refs } = parseTrailingReference(`fix the thing ([2411f73](${COMMIT_URL}))`)
    assert.equal(text, 'fix the thing')
    assert.equal(refs.issue, null)
    assert.deepEqual(refs.commit, { short: '2411f73', url: COMMIT_URL })
  })

  it('extracts both issue and commit references from one entry', () => {
    const raw = `certify Explore provenance ([#911](${ISSUE_URL})) ([2411f73](${COMMIT_URL}))`
    const { text, refs } = parseTrailingReference(raw)
    assert.equal(text, 'certify Explore provenance')
    assert.deepEqual(refs.issue, { number: '911', url: ISSUE_URL })
    assert.deepEqual(refs.commit, { short: '2411f73', url: COMMIT_URL })
  })

  it('leaves plain text untouched', () => {
    const { text, refs } = parseTrailingReference('no references here')
    assert.equal(text, 'no references here')
    assert.equal(refs.issue, null)
    assert.equal(refs.commit, null)
  })
})

describe('parseChangelog', () => {
  const markdown = [
    '## [0.1.9](compare-019) (2026-08-12)',
    '',
    '### Added',
    '',
    `* certify Explore provenance ([#911](${ISSUE_URL})) ([2411f73](${COMMIT_URL}))`,
    '* plain entry',
    '',
    '### Fixed',
    '',
    '## [0.1.8](compare-018) (2026-07-01)',
    '',
    '### Changed',
    '',
    '* later release entry',
  ].join('\n')

  it('parses releases, sections, and both reference kinds', () => {
    const releases = parseChangelog(markdown)
    assert.equal(releases[0].version, '0.1.9')
    const items = releases[0].sections.find(section => section.title === 'Added').items
    assert.deepEqual(items[0].issue, { number: '911', url: ISSUE_URL })
    assert.deepEqual(items[0].commit, { short: '2411f73', url: COMMIT_URL })
    assert.equal(items[1].text, 'plain entry')
  })

  it('drops sections without items', () => {
    const releases = parseChangelog(markdown)
    assert.equal(releases[0].sections.some(section => section.title === 'Fixed'), false)
    assert.equal(releases.length, 2)
    assert.deepEqual(releases[1].sections.map(section => section.title), ['Changed'])
  })
})

describe('buildRss', () => {
  it('embeds the clean version and escaped descriptions', () => {
    const releases = parseChangelog(
      ['## [0.1.9](compare) (2026-08-12)', '', '### Added', '', '* ship it'].join('\n'),
    )
    const rss = buildRss(releases)
    assert.match(rss, /<title>IBEX Harness v0\.1\.9<\/title>/)
    assert.match(rss, /releases\/tag\/v0\.1\.9</)
    assert.match(rss, /ship it/)
  })
})
