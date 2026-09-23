import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { prepareRun, suiteRoot, validateSuite } from '../../evaluation/product-modeling-dev-v1/scripts/suite.mjs'

const { manifest } = validateSuite()
assert.deepEqual(new Set(manifest.cases.map(item => item.kind)), new Set([
  'drawing-understanding', 'reference-to-model', 'guided-reference-to-model',
  'focused-module', 'parameter-change', 'text-to-model',
]))

const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-product-modeling-test-'))
try {
  const build = prepareRun({ caseId: 'task-lamp-build', output: path.join(scratch, 'build') })
  const buildFiles = fs.readdirSync(build.destination).sort()
  assert.deepEqual(buildFiles, ['attachments', 'brief.md', 'task.json'])
  assert.deepEqual(fs.readdirSync(path.join(build.destination, 'attachments')), ['task-lamp-multiview.png'])
  const publicTask = JSON.parse(fs.readFileSync(path.join(build.destination, 'task.json'), 'utf8'))
  assert.equal(publicTask.kind, 'reference-to-model')
  assert.ok(publicTask.files.every(file => /^[0-9a-f]{64}$/.test(file.sha256)))
  assert.doesNotMatch(JSON.stringify(publicTask), /evaluator|checklist|sourceRoot/i)
  assert.throws(() => prepareRun({ caseId: 'task-lamp-build', output: build.destination }), /already exists/)
  assert.throws(() => prepareRun({ caseId: 'task-lamp-change', output: path.join(scratch, 'missing') }), /baseline-hip/)

  const baseline = path.join(scratch, 'prior.hip')
  fs.writeFileSync(baseline, 'test HIP bytes')
  const changed = prepareRun({ caseId: 'task-lamp-change', output: path.join(scratch, 'change'), baselineHip: baseline })
  assert.deepEqual(fs.readFileSync(path.join(changed.destination, 'work.hip')), fs.readFileSync(baseline))
  assert.ok(changed.task.files.some(file => file.path === 'work.hip'))
  assert.deepEqual(fs.readdirSync(changed.destination).sort(), ['attachments', 'brief.md', 'task.json', 'work.hip'])

  const corrupted = path.join(scratch, 'corrupted-suite')
  fs.cpSync(suiteRoot, corrupted, { recursive: true })
  const manifestPath = path.join(corrupted, 'manifest.json')
  const altered = JSON.parse(fs.readFileSync(manifestPath, 'utf8'))
  altered.cases[0].public.attachments = [altered.cases[0].evaluator]
  fs.writeFileSync(manifestPath, JSON.stringify(altered))
  assert.throws(() => validateSuite(corrupted), /attachment is not public|attachment is not a PNG/)
  assert.throws(() => prepareRun({ caseId: 'task-lamp-build', output: path.join(suiteRoot, 'runs', 'should-reject') }), /outside the repository/)
} finally {
  const resolved = fs.realpathSync(scratch)
  if (!resolved.startsWith(path.resolve(os.tmpdir()) + path.sep) || !path.basename(resolved).startsWith('dsh-product-modeling-test-')) throw new Error('refusing cleanup outside test temp directory')
  fs.rmSync(resolved, { recursive: true, force: true })
}

console.log('product modeling development evaluation tests passed')
