import assert from 'node:assert/strict'
import {collectTargets, parseReleaseFeed} from '../check-dsh-updates.mjs'

const old = '2026-10-01T00:00:00Z', since = '2026-11-01T00:00:00Z', recent = '2026-11-03T12:00:00Z'
const sources = {
  npm: [{version:'0.1.9',date:old}, {version:'0.2.2',date:recent}, {version:'0.2.3-alpha.2',date:recent}],
  github: [{version:'0.2.3-alpha.3',date:recent}, {version:'0.2.3-alpha.4',date:recent}],
  stable: [{version:'0.2.2',date:recent,url:'https://example.org/stable.exe',sha512:'stable-digest'}],
  nightly: [{version:'0.2.3-alpha.4',date:recent,url:'https://example.org/nightly.exe',sha512:'nightly-digest'}],
}
const targets = collectTargets(sources, since, new Set(['0.2.3-alpha.2']))
assert.deepEqual(targets.map(t => t.version), ['0.2.2','0.2.3-alpha.3','0.2.3-alpha.4'],
  'A new stable backport and both prereleases between polls must survive')
assert.deepEqual(Object.keys(targets[0].sources).sort(), ['npm','stable'])
assert.deepEqual(Object.keys(targets[1].sources), ['github'], 'An upstream-only release remains visible as pending')
assert.equal(targets[2].sources.nightly.sha512, 'nightly-digest')
assert.deepEqual(collectTargets(sources, '2026-12-01T00:00:00Z', new Set()), [])
assert.throws(() => collectTargets(sources, 'invalid', new Set()), /timestamp/)
const atom = parseReleaseFeed(`<feed><updated>${recent}</updated><entry>
  <updated>${old}</updated><link rel="alternate" href="https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.2"/>
  <content type="html">&lt;entry&gt;other release&lt;/entry&gt;</content></entry></feed>`)
assert.equal(atom[0].version, '0.2.2')
assert.equal(atom[0].date, old, 'Use the release entry date, not the feed update time')
assert.throws(() => parseReleaseFeed('<feed/>'), /Empty GitHub/)
console.log('DSH discovery preserves backports, intermediate and upstream-only releases and coalesces channel evidence')
