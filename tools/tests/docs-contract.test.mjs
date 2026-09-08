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
assert.deepEqual(docs.filter(d => /handoff|交接/i.test(d.name)).map(d => d.name), ['handoff.md'],
  'use one rolling handoff, not dated or parallel copies')

// A bounded current handoff is the sole exception to the no-process-doc rule.
// This validates shape and budget; only a human/code review can confirm that
// an implementation actually satisfies an item's removal criteria.
function checkHandoff(text) {
  assert(text.length <= 8000, 'handoff exceeds 8000 characters; prune/merge resolved work')
  assert(text.split('\n').length <= 120, 'handoff exceeds 120 lines')
  assert.match(text, /^# 当前开发交接\n/)
  const date = text.match(/^核对日期：(\d{4}-\d{2}-\d{2})$/m)?.[1]
  assert(date && !Number.isNaN(Date.parse(date)) && new Date(date).toISOString().slice(0, 10) === date,
    'handoff needs a valid checked date')
  assert.doesNotMatch(text, /^\s*- \[[xX]\]/m, 'remove completed handoff items instead of retaining checked boxes')
  assert.doesNotMatch(text, /\]\([^)]*(?:tools\/out|\.research)[^)]*\)/,
    'handoff must not depend on ignored local evidence links')
  const entries = [...text.matchAll(/^### (H-\d{2}) (.+)\n([\s\S]*?)(?=^### |$(?![\s\S]))/gm)]
  const headings = text.split('\n').filter(line => /^#{2,6} /.test(line))
  assert(headings.every(line => line === '## 待交接事项' || /^### H-\d{2} .+/.test(line)),
    'handoff has unexpected history/completed sections')
  assert(entries.length <= 8, 'handoff exceeds 8 active items')
  assert.equal(new Set(entries.map(e => e[1])).size, entries.length, 'handoff ids must be unique')
  if (!entries.length) assert.match(text, /当前无待交接事项/, 'empty handoff must say no pending work')
  else assert(!text.includes('当前无待交接事项'), 'active handoff cannot claim no pending work')
  for (const [, id, , body] of entries) {
    for (const field of ['状态', '现状', '下一步', '移除条件', '入口']) {
      assert.equal([...body.matchAll(new RegExp(`^- ${field}：\\S.*$`, 'gm'))].length, 1,
        `${id} requires exactly one nonempty ${field}`)
    }
    assert.match(body, /^- 状态：(待修复|待验证|待决策)$/m, `${id} closed work must be removed`)
    assert.match(body, /^- 入口：.*\]\(/m, `${id} needs a repository source/verification link`)
  }
}
checkHandoff(read('docs/handoff.md'))
const sample = '# 当前开发交接\n\n核对日期：2026-09-09\n\n## 待交接事项\n\n'
  + '### H-01 示例\n\n- 状态：待验证\n- 现状：已有实现但缺验证\n- 下一步：运行对应回归\n'
  + '- 移除条件：实际验证完成\n- 入口：[测试](../tools/tests/docs-contract.test.mjs)。\n'
checkHandoff(sample)
checkHandoff('# 当前开发交接\n\n核对日期：2026-09-09\n\n当前无待交接事项。\n')
for (const invalid of [sample.replace('状态：待验证', '状态：已完成'),
  sample.replace('- 下一步：运行对应回归\n', ''),
  sample + sample.slice(sample.indexOf('### H-01')),
  sample + '\n- [x] 已实现\n', sample + '\n## 历史完成记录\n',
  sample + 'a'.repeat(8001), sample + '\n'.repeat(121),
  sample.replace('2026-09-09', '2026-02-30'),
  sample.replace('../tools/tests/docs-contract.test.mjs', '../tools/out/only-local.md'),
  sample + Array.from({length:8}, (_, i) => sample.slice(sample.indexOf('### H-01')).replace('H-01', 'H-0'+(i+2))).join('\n')]) {
  assert.throws(() => checkHandoff(invalid), 'invalid handoff must fail without being silently rewritten')
}
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
