import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { sealInstance } from '../benchmark-instance.mjs'
import { sha256File, validateEvaluatorSpec, validateSealedInstanceManifest } from '../benchmark-manifest.mjs'

const hash = 'a'.repeat(64)
const commit = 'b'.repeat(40)
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-sealed-instance-test-'))
try {
  const briefFile = path.join(root, 'brief.json')
  const brief = {
    schemaVersion: 1,
    briefId: 'mechanical-calibration-v1',
    capabilityFamily: 'mechanical',
    instanceRole: 'calibration',
    language: 'zh-CN',
    agentMessage: 'Create an editable procedural asset and save it under $HIP.',
    resources: [],
    evaluatorMaterialExposed: false,
  }
  fs.writeFileSync(briefFile, JSON.stringify(brief))
  const briefHash = sha256File(briefFile)

  const answersFile = path.join(root, 'answers.json')
  fs.writeFileSync(answersFile, JSON.stringify({
    schemaVersion: 1,
    answerSetId: 'mechanical-calibration-v1-answers',
    publicBriefSha256: briefHash,
    entries: [],
  }))

  const seedFile = path.join(root, 'seed.json')
  fs.writeFileSync(seedFile, JSON.stringify({
    schemaVersion: 1,
    fixtureId: 'generic-mechanical-calibration-v1',
    capabilityFamily: 'mechanical',
    instanceRole: 'calibration',
    generator: {
      id: 'dsh-houdini-generic-seed', version: '1', scriptSha256: hash,
      parametersSha256: hash, deterministic: true,
    },
    output: { hip: '$HIP/seed.hip', sha256: hash, identitySha256: hash, houdini: '21.0.440' },
    evaluatorMaterialExposed: false,
  }))

  const evaluatorFile = path.join(root, 'evaluator.json')
  const evaluator = {
    schemaVersion: 1,
    specId: 'mechanical-calibration-v1-evaluator',
    capabilityFamily: 'mechanical',
    instanceRole: 'calibration',
    publicBriefSha256: briefHash,
    criteria: [
      { criterionId: 'core', dimension: 'coreDelivery', maxPoints: 40, requirement: 'Core delivery works.', evidence: ['deterministic'], critical: true },
      { criterionId: 'objective', dimension: 'objectiveEvidence', maxPoints: 25, requirement: 'Evidence is reproducible.', evidence: ['deterministic', 'trace'], critical: false },
      { criterionId: 'visual', dimension: 'independentVisual', maxPoints: 25, requirement: 'Independent visual result supports the goal.', evidence: ['blind-visual', 'target-visual'], critical: false },
      { criterionId: 'honest', dimension: 'honestDelivery', maxPoints: 10, requirement: 'Final report preserves uncertainty.', evidence: ['trace'], critical: false },
    ],
    hardFailures: [{ failureId: 'core-missing', criterionId: 'core', condition: 'Core output is absent.' }],
    scoreThreshold: 75,
    evaluatorMaterialExposed: false,
  }
  fs.writeFileSync(evaluatorFile, JSON.stringify(evaluator))

  assert.equal(validateEvaluatorSpec(evaluator, { publicBriefSha256: briefHash }), evaluator)
  const sealed = sealInstance({
    publicBriefFile: briefFile,
    allowedAnswersFile: answersFile,
    seedFixtureFile: seedFile,
    evaluatorSpecFile: evaluatorFile,
    productionSurfaceCommit: commit,
  })
  assert.equal(validateSealedInstanceManifest(sealed.manifest), sealed.manifest)
  assert.match(sealed.sealedInstanceSha256, /^[0-9a-f]{64}$/)
  assert.equal(sealed.manifest.instanceId, brief.briefId)
  assert.deepEqual(sealed.manifest.files.resourceSha256, [])

  assert.throws(() => validateEvaluatorSpec({
    ...evaluator,
    criteria: evaluator.criteria.map((item) => item.criterionId === 'objective' ? { ...item, maxPoints: 24 } : item),
  }), /objectiveEvidence criteria must total exactly 25/)
  assert.throws(() => validateEvaluatorSpec({
    ...evaluator,
    hardFailures: [{ failureId: 'bad', criterionId: 'missing', condition: 'Missing.' }],
  }), /unknown criterionId/)
  assert.throws(() => sealInstance({
    publicBriefFile: briefFile,
    allowedAnswersFile: answersFile,
    seedFixtureFile: seedFile,
    evaluatorSpecFile: evaluatorFile,
    resourceFiles: new Map([['unexpected', evaluatorFile]]),
    productionSurfaceCommit: commit,
  }), /resource mappings must exactly match/)
} finally {
  fs.rmSync(root, { recursive: true, force: true })
}

console.log('sealed benchmark instance contract tests passed')
