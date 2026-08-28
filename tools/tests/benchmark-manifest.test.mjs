import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  agentSurfaceHash,
  canonicalJson,
  listAgentSurfaceFiles,
  sha256Json,
  validateProtocolManifest,
  validateRunManifest,
} from '../benchmark-manifest.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const hash = 'a'.repeat(64)
const git = 'b'.repeat(40)

assert.equal(canonicalJson({ z: 1, a: { d: 2, c: 3 } }), '{"a":{"c":3,"d":2},"z":1}')
assert.equal(sha256Json({ a: 1, b: 2 }), sha256Json({ b: 2, a: 1 }))
const currentSurfaceHash = agentSurfaceHash(root)
assert.match(currentSurfaceHash, /^[0-9a-f]{64}$/)
assert.ok(listAgentSurfaceFiles(root).includes('presets/houdini/agent.cordis.yml'))
assert.ok(listAgentSurfaceFiles(root).includes('skills/houdini-sop-workflow/SKILL.md'))

const baseline = JSON.parse(fs.readFileSync(path.join(root, 'benchmark', 'baseline.json'), 'utf8'))
assert.equal(currentSurfaceHash, baseline.agentSurfaceSha256, 'agent-visible surface drifted after the benchmark baseline was sealed')

const protocol = {
  schemaVersion: 1,
  protocolVersion: 'b0-test',
  createdAt: '2026-08-28T00:00:00.000Z',
  baselineCommit: git,
  agentSurfaceSha256: hash,
  environment: {
    houdini: 'test-houdini',
    dsh: 'test-dsh',
    plugin: 'test-plugin',
    visionToolkit: 'test-vision',
  },
  execution: {
    models: ['model-a', 'model-b'],
    budget: { wallMinutes: 1, maxTurns: 1 },
    additionalCorrectionLimit: 0,
  },
  evaluation: {
    deterministicEvaluator: 'deterministic-v1',
    blindVisualEvaluator: 'blind-v1',
    targetEvaluator: 'target-v1',
    blindPromptSha256: hash,
    targetPromptSha256: hash,
  },
  sealedInstances: Object.fromEntries(
    ['mechanical', 'simulation', 'lookdev'].map((family) => [family, {
      calibration: hash,
      holdout: hash,
      counterexample: hash,
    }]),
  ),
}
assert.equal(validateProtocolManifest(protocol), protocol)
assert.throws(() => validateProtocolManifest({ ...protocol, execution: { models: ['model-a', 'model-a'], additionalCorrectionLimit: 0 } }), /two distinct/)

const run = {
  schemaVersion: 1,
  runId: 'run-test',
  protocolVersion: 'b0-test',
  protocolManifestSha256: hash,
  baselineCommit: git,
  agentSurfaceSha256: hash,
  phase: 'discovery',
  capabilityFamily: 'mechanical',
  instanceRole: 'calibration',
  model: 'model-a',
  instanceSealedSha256: hash,
  evaluatorSpecSha256: hash,
  agentExposure: {
    publicBriefSha256: hash,
    allowedAnswersSha256: hash,
    seedSceneSha256: hash,
    resourceSha256: [],
    evaluatorMaterialExposed: false,
  },
  startedAt: '2026-08-28T00:00:00.000Z',
  status: 'running',
}
assert.equal(validateRunManifest(run), run)
assert.throws(() => validateRunManifest({
  ...run,
  agentExposure: { ...run.agentExposure, evaluatorMaterialExposed: true },
}), /invalidate contaminated runs/)

for (const schema of ['protocol-manifest.schema.json', 'run-manifest.schema.json']) {
  const parsed = JSON.parse(fs.readFileSync(path.join(root, 'benchmark', schema), 'utf8'))
  assert.equal(parsed.$schema, 'https://json-schema.org/draft/2020-12/schema')
  assert.equal(parsed.additionalProperties, false)
}

const packageJson = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'))
assert.ok(!packageJson.files.includes('benchmark'), 'sealed benchmark administration must not ship in the production npm package')

console.log('benchmark manifest and surface-hash tests passed')
