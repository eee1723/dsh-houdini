import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { suiteRoot, validateSuite } from '../../evaluation/product-modeling-dev-v1/scripts/suite.mjs'
import { validateReviewResult } from '../../evaluation/product-modeling-dev-v1/scripts/review.mjs'

const { manifest } = validateSuite()
const item = manifest.cases.find(entry => entry.id === 'task-lamp-build')
const checklist = JSON.parse(fs.readFileSync(path.join(suiteRoot, item.evaluator), 'utf8'))
const makeReview = () => ({
  suiteId: manifest.suiteId,
  caseId: item.id,
  reviewer: { id: 'test-reviewer', mode: 'manual-independent', reviewedAt: '2026-09-24T00:00:00Z' },
  run: { runId: 'test-run', agentModel: 'test-model', agentModelVersion: '1', runtimeIdentity: 'test-runtime', wallTimeSeconds: 0, budgetDescription: 'test only' },
  evidence: [
    { id: 'submitted', origin: 'agentSubmitted', path: 'submitted.hip', notes: '' },
    { id: 'independent', origin: 'reviewerProduced', path: 'independent.png', notes: '' },
    { id: 'reference', origin: 'source', path: 'reference.png', notes: '' },
  ],
  criteria: checklist.criteria.map(criterion => ({ id: criterion.id, status: 'unverified', evidenceIds: ['independent'], reason: 'test only' })),
  conclusion: { agentClaim: 'unclear', reviewerJudgement: 'unverified', summary: 'test only' },
})

assert.equal(validateReviewResult(makeReview()).caseId, item.id)

const invalidCases = [
  [review => { review.caseId = 'not-a-case' }, /caseId is not in the suite/],
  [review => { review.criteria.pop() }, /criterion IDs do not match/],
  [review => { review.criteria.push({ ...review.criteria[0] }) }, /duplicate criterion IDs/],
  [review => { review.criteria[0].id = 'not-a-criterion' }, /criterion IDs do not match/],
  [review => { review.criteria[0].evidenceIds = ['missing'] }, /unknown evidence ID/],
  [review => { review.evidence.push({ ...review.evidence[0] }) }, /duplicate evidence IDs/],
  [review => { review.evidence[0].origin = 'agentSelfReview' }, /origin has an invalid value/],
  [review => { review.criteria[0].status = 'skipped' }, /status has an invalid value/],
  [review => { review.reviewer.mode = 'agent' }, /mode has the wrong fixed value/],
  [review => { review.evidence = review.evidence.filter(item => item.origin !== 'reviewerProduced'); review.criteria.forEach(criterion => { criterion.evidenceIds = ['submitted'] }) }, /independently produced evidence/],
  [review => { review.criteria[0].status = 'pass'; review.criteria[0].evidenceIds = ['submitted'] }, /passed criterion needs independent evidence/],
]
for (const [alter, expectedError] of invalidCases) {
  const review = makeReview()
  alter(review)
  assert.throws(() => validateReviewResult(review), expectedError)
}

const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-product-modeling-review-test-'))
try {
  const script = fileURLToPath(new URL('../../evaluation/product-modeling-dev-v1/scripts/validate-review.mjs', import.meta.url))
  const goodFile = path.join(scratch, 'good.json')
  fs.writeFileSync(goodFile, JSON.stringify(makeReview()))
  const good = spawnSync(process.execPath, [script, goodFile], { encoding: 'utf8' })
  assert.equal(good.status, 0, good.stderr)
  assert.match(good.stdout, /validated review:/)

  const badFile = path.join(scratch, 'bad.json')
  const badReview = makeReview()
  badReview.criteria[0].evidenceIds = ['missing']
  fs.writeFileSync(badFile, JSON.stringify(badReview))
  const bad = spawnSync(process.execPath, [script, badFile], { encoding: 'utf8' })
  assert.equal(bad.status, 1)
  assert.match(bad.stderr, /unknown evidence ID/)
  assert.deepEqual(fs.readdirSync(scratch).sort(), ['bad.json', 'good.json'])
} finally {
  const resolved = fs.realpathSync(scratch)
  if (!resolved.startsWith(path.resolve(os.tmpdir()) + path.sep) || !path.basename(resolved).startsWith('dsh-product-modeling-review-test-')) throw new Error('refusing cleanup outside test temp directory')
  fs.rmSync(resolved, { recursive: true, force: true })
}

console.log('product modeling review validation tests passed')
