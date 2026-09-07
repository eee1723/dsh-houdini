import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import os from 'node:os'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { renderNodeCards, validateNodeCards, sourcePath, outputPath } from '../gen-node-card-docs.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const read = p => fs.readFileSync(path.join(root, p), 'utf8').replaceAll('\r\n', '\n')
const data = JSON.parse(read(sourcePath))
assert.equal(read(outputPath), renderNodeCards(data), 'generated node-card documentation drifted')
const altered = structuredClone(data)
altered.cards.sweep.notes.push('A new source fact must change the generated reference.')
assert.notEqual(renderNodeCards(altered), read(outputPath))
for (const c of Object.values(data.cards)) {
  for (const note of c.notes) assert.ok(read(outputPath).includes(note), `missing note: ${c.id}`)
  for (const d of c.decisions || []) assert.ok(read(outputPath).includes(d.guidance), `missing decision: ${c.id}/${d.id}`)
}
const invalid = structuredClone(data)
invalid.cards.sweep.decisions[0].any_of = [['invented_field']]
assert.throws(() => validateNodeCards(invalid), /critical_parameters/)
const extra = structuredClone(data)
extra.cards.sweep.unrendered_field = 'must not be silently omitted'
assert.throws(() => renderNodeCards(extra), /unsupported/)
const duplicate = structuredClone(data)
duplicate.cards.tube.id = duplicate.cards.sphere.id
assert.throws(() => renderNodeCards(duplicate), /duplicate/)

// Exercise the real CLI in an isolated fixture: check must fail without fixing drift.
const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-doc-contract-'))
try {
  for (const dir of ['tools', 'houdini', 'docs']) fs.mkdirSync(path.join(fixture, dir))
  fs.copyFileSync(path.join(root, 'tools/gen-node-card-docs.mjs'), path.join(fixture, 'tools/gen-node-card-docs.mjs'))
  fs.writeFileSync(path.join(fixture, sourcePath), JSON.stringify(data))
  const run = (...args) => spawnSync(process.execPath, [path.join(fixture, 'tools/gen-node-card-docs.mjs'), ...args], { encoding: 'utf8', windowsHide: true })
  assert.equal(run('--check').status, 1, 'missing document must fail check')
  assert.ok(!fs.existsSync(path.join(fixture, outputPath)), 'check must not create a file')
  assert.equal(run().status, 0)
  assert.equal(run('--check').status, 0)
  fs.appendFileSync(path.join(fixture, outputPath), 'manual drift\n')
  const drifted = fs.readFileSync(path.join(fixture, outputPath), 'utf8')
  assert.equal(run('--check').status, 1)
  assert.equal(fs.readFileSync(path.join(fixture, outputPath), 'utf8'), drifted)
  assert.equal(run().status, 0)
  assert.equal(fs.readFileSync(path.join(fixture, outputPath), 'utf8'), renderNodeCards(data))
} finally {
  assert.equal(path.dirname(fixture), path.resolve(os.tmpdir()))
  assert.ok(path.basename(fixture).startsWith('dsh-doc-contract-'))
  fs.rmSync(fixture, { recursive: true, force: true })
}

const docs = fs.readdirSync(path.join(root, 'docs'), { withFileTypes: true })
assert.ok(docs.every(d => d.isFile() && d.name.endsWith('.md')), 'docs is a flat current-design library, not an artifact/archive directory')
const index = read('docs/README.md')
for (const file of docs) {
  if (file.name !== 'README.md') assert.ok(index.includes(`](${file.name})`), `unindexed document ${file.name}`)
}
const docFiles = ['README.md', 'AGENTS.md', ...docs.map(d => 'docs/' + d.name)]
for (const file of docFiles) {
  const content = read(file)
  // Check actual Markdown links, not command examples or arbitrary code strings.
  const prose = content.replace(/```[\s\S]*?```/g, '')
  for (const match of prose.matchAll(/\[[^\]]*\]\(([^)]+)\)/g)) {
    const href = match[1].replace(/^<|>$/g, '')
    if (/^[a-z][a-z0-9+.-]*:/i.test(href)) continue
    const [target, anchor] = href.split('#')
    const resolved = path.resolve(root, path.dirname(file), decodeURIComponent(target || ''))
    const destination = target ? resolved : path.join(root, file)
    assert.ok(fs.existsSync(destination), `${file}: dead link ${href}`)
    if (anchor && fs.statSync(destination).isFile() && destination.endsWith('.md')) {
      const headings = fs.readFileSync(destination, 'utf8').split(/\r?\n/)
        .filter(l => /^#{1,6} /.test(l)).map(l => l.replace(/^#+ /, '').toLowerCase()
          .replace(/[^\p{L}\p{N}\s_-]/gu, '').replace(/\s/g, '-'))
      assert.ok(headings.includes(decodeURIComponent(anchor)), `${file}: missing heading ${href}`)
    }
  }
  assert.doesNotMatch(content, /^#{1,6} .*?(?:20\d\d-\d\d-\d\d|v\d+\s*候选|本轮|实施进度|Phase [A-Z])/m,
    `${file}: iteration-log headings do not belong in current docs`)
}
const architecture = read('docs/architecture.md')
for (const [dir, suffix] of [['src', '.ts'], ['houdini/python3.11libs', '.py']]) {
  for (const name of fs.readdirSync(path.join(root, dir)).filter(n => n.endsWith(suffix))) {
    assert.ok(architecture.includes(`](../${dir}/${name})`), `production module has no architecture entry: ${dir}/${name}`)
  }
}
console.log(`documentation contracts passed (${docs.length} current docs, ${Object.keys(data.cards).length} generated cards)`)
