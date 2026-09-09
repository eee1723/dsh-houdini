import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { sha256Json, validateSeedFixture } from '../benchmark-manifest.mjs'
import {
  buildSeedFixtureManifest,
  seedParametersSha256,
  validateSeedGeneratorInput,
} from '../benchmark-seed.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const generatorScript = path.join(root, 'tools', 'benchmark-seed-hython.py')
const trackedInputs = ['mechanical', 'simulation', 'lookdev'].map((family) => (
  JSON.parse(fs.readFileSync(path.join(root, 'benchmark', 'seed-inputs', `${family}-calibration.json`), 'utf8'))
))
for (const trackedInput of trackedInputs) validateSeedGeneratorInput(trackedInput)
assert.deepEqual(trackedInputs.map((item) => item.capabilityFamily).sort(), ['lookdev', 'mechanical', 'simulation'])
assert.equal(trackedInputs.find((item) => item.capabilityFamily === 'lookdev').scene.geometryPreset, 'shaderball')
assert.ok(trackedInputs.filter((item) => item.capabilityFamily !== 'lookdev').every((item) => item.scene.mode === 'empty'))

const input = {
  schemaVersion: 1,
  fixtureId: 'generic-empty-mechanical-calibration',
  capabilityFamily: 'mechanical',
  instanceRole: 'calibration',
  generatorVersion: '1',
  output: { hip: '$HIP/seeds/generic-empty.hip' },
  scene: {
    mode: 'empty',
    geometryPreset: 'none',
    clearExisting: true,
    fps: 24,
    frameRange: { start: 1, end: 120 },
    playbackRange: { start: 1, end: 96 },
    currentFrame: 1,
  },
  evaluatorMaterialExposed: false,
}

assert.equal(validateSeedGeneratorInput(input), input)
assert.throws(() => validateSeedGeneratorInput({ ...input, evaluatorHint: 'hidden' }), /unsupported field/)
assert.throws(() => validateSeedGeneratorInput({ ...input, evaluatorMaterialExposed: true }), /must not expose/)
assert.throws(() => validateSeedGeneratorInput({
  ...input,
  scene: { ...input.scene, playbackRange: { start: 0, end: 96 } },
}), /must stay inside/)
assert.throws(() => validateSeedGeneratorInput({
  ...input,
  scene: { ...input.scene, geometryPreset: 'shaderball' },
}), /must be "none"/)
assert.equal(validateSeedGeneratorInput({
  ...input,
  fixtureId: 'generic-lookdev-calibration',
  capabilityFamily: 'lookdev',
  scene: { ...input.scene, mode: 'fixed-geometry', geometryPreset: 'shaderball' },
}).scene.geometryPreset, 'shaderball')
assert.throws(() => validateSeedGeneratorInput({
  ...input,
  output: { hip: '$HIP/../escape.hip' },
}), /below \$HIP/)

const sameParametersDifferentFixture = {
  ...input,
  fixtureId: 'generic-empty-simulation-holdout',
  capabilityFamily: 'simulation',
  instanceRole: 'holdout',
}
assert.equal(seedParametersSha256(input), seedParametersSha256(sameParametersDifferentFixture))

const hipRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-benchmark-seed-unit-'))
try {
  const outputPath = path.join(hipRoot, 'seeds', 'generic-empty.hip')
  fs.mkdirSync(path.dirname(outputPath), { recursive: true })
  fs.writeFileSync(outputPath, 'deterministic HIP fixture bytes')
  const identity = {
    schemaVersion: 1,
    houdini: '21.0.440',
    fps: 24,
    frameRange: [1, 120],
    playbackRange: [1, 96],
    currentFrame: 1,
    nodes: [],
  }
  const manifest = buildSeedFixtureManifest({
    input,
    hipRoot,
    generatorScript,
    runnerResult: { ok: true, outputPath, houdini: '21.0.440', identity },
  })
  assert.equal(manifest.generator.id, 'dsh-houdini-generic-seed')
  assert.equal(manifest.generator.parametersSha256, seedParametersSha256(input))
  assert.equal(manifest.output.identitySha256, sha256Json(identity))
  assert.equal(validateSeedFixture(manifest, { hipRoot }).fixtureId, input.fixtureId)
  const alias = path.join(hipRoot, 'seeds-alias')
  fs.symlinkSync(path.dirname(outputPath), alias, process.platform === 'win32' ? 'junction' : 'dir')
  const aliased = buildSeedFixtureManifest({
    input, hipRoot, generatorScript,
    runnerResult: { ok: true, outputPath: path.join(alias, path.basename(outputPath)), houdini: '21.0.440', identity },
  })
  assert.equal(aliased.output.sha256, manifest.output.sha256, 'path aliases must identify the same existing HIP')
  assert.throws(() => buildSeedFixtureManifest({
    input,
    hipRoot,
    generatorScript,
    runnerResult: { ok: true, outputPath: path.join(hipRoot, 'other.hip'), houdini: '21.0.440', identity },
  }), /does not point/)
} finally {
  fs.rmSync(hipRoot, { recursive: true, force: true })
}

console.log('benchmark seed generator contract tests passed')
