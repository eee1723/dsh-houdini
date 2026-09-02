import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { prepareIsolatedRunWorkspace, prepareSmokeWorkspace } from '../benchmark-smoke.mjs'
import { sha256File, sha256Json } from '../benchmark-manifest.mjs'

const hash = 'a'.repeat(64)
const commit = 'b'.repeat(40)
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-smoke-preparer-'))
try {
  const operator = path.join(root, 'operator', 'mechanical')
  const hipRoot = path.join(root, 'hip', 'mechanical')
  fs.mkdirSync(operator, { recursive: true })
  fs.mkdirSync(path.join(hipRoot, 'seed'), { recursive: true })
  const brief = { schemaVersion: 1, briefId: 'm', capabilityFamily: 'mechanical', instanceRole: 'calibration', language: 'zh-CN', agentMessage: 'Build a test asset.', resources: [], evaluatorMaterialExposed: false }
  fs.writeFileSync(path.join(operator, 'public-brief.json'), JSON.stringify(brief))
  fs.writeFileSync(path.join(operator, 'agent-message.txt'), brief.agentMessage)
  fs.writeFileSync(path.join(operator, 'allowed-answers.json'), '{}')
  fs.writeFileSync(path.join(operator, 'evaluator-spec.json'), '{}')
  fs.writeFileSync(path.join(hipRoot, 'seed', 'seed.hip'), 'seed bytes')
  const seed = { schemaVersion: 1, fixtureId: 'seed', capabilityFamily: 'mechanical', instanceRole: 'calibration', generator: { id: 'g', version: '1', scriptSha256: hash, parametersSha256: hash, deterministic: true }, output: { hip: '$HIP/seed/seed.hip', sha256: sha256File(path.join(hipRoot, 'seed', 'seed.hip')), identitySha256: hash, houdini: '21.0.440' }, evaluatorMaterialExposed: false }
  fs.writeFileSync(path.join(operator, 'seed-fixture.json'), JSON.stringify(seed))
  const sealed = { schemaVersion: 1, instanceId: 'm', capabilityFamily: 'mechanical', instanceRole: 'calibration', files: { publicBriefSha256: sha256File(path.join(operator, 'public-brief.json')), allowedAnswersSha256: sha256File(path.join(operator, 'allowed-answers.json')), seedFixtureSha256: sha256File(path.join(operator, 'seed-fixture.json')), evaluatorSpecSha256: sha256File(path.join(operator, 'evaluator-spec.json')), resourceSha256: [] }, releasePolicy: { productionSurfaceCommit: commit, revealAfterSurfaceFreeze: true, becomesCalibrationAfterReveal: true }, evaluatorMaterialExposed: false }
  fs.writeFileSync(path.join(operator, 'sealed-manifest.json'), JSON.stringify(sealed))
  const protocol = { schemaVersion: 1, protocolVersion: 'p1', createdAt: '2026-09-01T00:00:00Z', baselineCommit: commit, agentSurfaceSha256: hash, environment: { houdini: '21', dsh: '1', plugin: '1', visionToolkit: '1' }, execution: { models: ['model-a', 'model-b'], budget: { wallMinutes: 1, maxTurns: 1 }, workspace: { mode: 'isolated-run-directory', seedHandling: 'copy-exact-bytes-to-work.hip', agentVisibleFiles: ['agent-message.txt', 'work.hip'], evaluatorMaterialAccessible: false }, additionalCorrectionLimit: 0 }, evaluation: { deterministicEvaluator: 'd', blindVisualEvaluator: 'b', targetEvaluator: 't', responseNormalizer: 'evaluator-json-normalizer-v2', blindPromptSha256: hash, targetPromptSha256: 'c'.repeat(64) }, sealedInstances: { mechanical: { calibration: sha256Json(sealed), holdout: hash, counterexample: hash }, simulation: { calibration: hash, holdout: hash, counterexample: hash }, lookdev: { calibration: hash, holdout: hash, counterexample: hash } } }
  const protocolFile = path.join(root, 'protocol.json')
  fs.writeFileSync(protocolFile, JSON.stringify(protocol))
  const prepared = prepareSmokeWorkspace({ kitRoot: root, family: 'mechanical', runId: 'smoke-1', protocolFile })
  assert.equal(prepared.evaluatorMaterialExposed, false)
  assert.deepEqual(prepared.agentVisibleFiles, ['agent-message.txt', 'work.hip'])
  assert.equal(sha256File(prepared.workHip), seed.output.sha256)
  assert.throws(() => prepareSmokeWorkspace({ kitRoot: root, family: 'mechanical', runId: 'smoke-1', protocolFile }), /already exists/)
  const formal = prepareIsolatedRunWorkspace({ kitRoot: root, family: 'mechanical', runId: 'formal-1', protocolFile, phase: 'discovery', model: 'model-b' })
  assert.equal(formal.phase, 'discovery')
  assert.equal(formal.model, 'model-b')
  assert.deepEqual(formal.agentVisibleFiles, ['agent-message.txt', 'work.hip'])
  assert.throws(() => prepareIsolatedRunWorkspace({ kitRoot: root, family: 'mechanical', runId: 'bad-model', protocolFile, phase: 'discovery', model: 'model-c' }), /not frozen/)
  assert.throws(() => prepareIsolatedRunWorkspace({ kitRoot: root, family: 'mechanical', runId: 'bad-phase', protocolFile, phase: 'generalization', model: 'model-a' }), /unsupported isolated run phase/)
} finally {
  fs.rmSync(root, { recursive: true, force: true })
}

console.log('isolated smoke workspace preparer tests passed')
