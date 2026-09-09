import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  resolveHipArtifactPath,
  sha256File,
  sha256Json,
  validateSeedFixture,
} from './benchmark-manifest.mjs'

const here = path.dirname(fileURLToPath(import.meta.url))
const defaultGeneratorScript = path.join(here, 'benchmark-seed-hython.py')
const FAMILIES = ['mechanical', 'simulation', 'lookdev']
const ROLES = ['calibration', 'holdout', 'counterexample']
const INPUT_KEYS = [
  'schemaVersion', 'fixtureId', 'capabilityFamily', 'instanceRole',
  'generatorVersion', 'output', 'scene', 'evaluatorMaterialExposed',
]

function requireObject(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${label} must be an object`)
  return value
}

function requireExactKeys(value, allowed, label) {
  const unsupported = Object.keys(value).filter((key) => !allowed.includes(key))
  const missing = allowed.filter((key) => !(key in value))
  if (unsupported.length) throw new Error(`${label} has unsupported field(s): ${unsupported.join(', ')}`)
  if (missing.length) throw new Error(`${label} is missing field(s): ${missing.join(', ')}`)
}

function requireFiniteNumber(value, label) {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(`${label} must be a finite number`)
  return value
}

function validateRange(value, label) {
  requireObject(value, label)
  requireExactKeys(value, ['start', 'end'], label)
  const start = requireFiniteNumber(value.start, `${label}.start`)
  const end = requireFiniteNumber(value.end, `${label}.end`)
  if (start > end) throw new Error(`${label}.start must not exceed ${label}.end`)
  return { start, end }
}

export function validateSeedGeneratorInput(input) {
  requireObject(input, 'seed generator input')
  requireExactKeys(input, INPUT_KEYS, 'seed generator input')
  if (input.schemaVersion !== 1) throw new Error('seed generator input schemaVersion must be 1')
  if (typeof input.fixtureId !== 'string' || !/^[a-z0-9][a-z0-9._-]*$/.test(input.fixtureId)) {
    throw new Error('fixtureId must use lowercase letters, digits, dots, underscores, or hyphens')
  }
  if (!FAMILIES.includes(input.capabilityFamily)) throw new Error('capabilityFamily is invalid')
  if (!ROLES.includes(input.instanceRole)) throw new Error('instanceRole is invalid')
  if (input.generatorVersion !== '1') throw new Error('generatorVersion must be "1"')
  if (input.evaluatorMaterialExposed !== false) throw new Error('seed input must not expose evaluator material')

  requireObject(input.output, 'output')
  requireExactKeys(input.output, ['hip'], 'output')
  if (typeof input.output.hip !== 'string' || !/^\$HIP\/.+\.hip(?:lc|nc)?$/i.test(input.output.hip)) {
    throw new Error('output.hip must name a .hip, .hiplc, or .hipnc file below $HIP')
  }
  const outputSegments = input.output.hip.slice('$HIP/'.length).split('/')
  if (outputSegments.some((segment) => segment === '' || segment === '.' || segment === '..')) {
    throw new Error('output.hip must stay below $HIP without empty, dot, or parent segments')
  }

  requireObject(input.scene, 'scene')
  requireExactKeys(input.scene, [
    'mode', 'geometryPreset', 'clearExisting', 'fps', 'frameRange', 'playbackRange', 'currentFrame',
  ], 'scene')
  if (!['empty', 'fixed-geometry'].includes(input.scene.mode)) {
    throw new Error('scene.mode must be "empty" or "fixed-geometry"')
  }
  const expectedPreset = input.scene.mode === 'empty' ? 'none' : 'shaderball'
  if (input.scene.geometryPreset !== expectedPreset) {
    throw new Error(`scene.geometryPreset must be "${expectedPreset}" when mode is "${input.scene.mode}"`)
  }
  if (input.scene.clearExisting !== true) throw new Error('scene.clearExisting must be true')
  const fps = requireFiniteNumber(input.scene.fps, 'scene.fps')
  if (!(fps > 0 && fps <= 240)) throw new Error('scene.fps must be greater than 0 and at most 240')
  const frameRange = validateRange(input.scene.frameRange, 'scene.frameRange')
  const playbackRange = validateRange(input.scene.playbackRange, 'scene.playbackRange')
  const currentFrame = requireFiniteNumber(input.scene.currentFrame, 'scene.currentFrame')
  if (playbackRange.start < frameRange.start || playbackRange.end > frameRange.end) {
    throw new Error('scene.playbackRange must stay inside scene.frameRange')
  }
  if (currentFrame < frameRange.start || currentFrame > frameRange.end) {
    throw new Error('scene.currentFrame must stay inside scene.frameRange')
  }
  return input
}

export function seedParametersSha256(input) {
  validateSeedGeneratorInput(input)
  return sha256Json(input.scene)
}

function parseRunnerOutput(stdout) {
  const lines = String(stdout || '').split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    if (!lines[index].startsWith('{')) continue
    try {
      return JSON.parse(lines[index])
    } catch {
      // Houdini startup diagnostics can precede the final JSON line.
    }
  }
  throw new Error(`Hython seed runner did not return JSON: ${String(stdout || '').slice(-1000)}`)
}

export function runSeedHython({ hython, generatorScript = defaultGeneratorScript, outputPath, scene }) {
  if (!path.isAbsolute(hython) || !fs.existsSync(hython)) throw new Error(`hython executable does not exist: ${hython}`)
  if (!path.isAbsolute(generatorScript) || !fs.existsSync(generatorScript)) {
    throw new Error(`seed generator script does not exist: ${generatorScript}`)
  }
  const requestRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-houdini-seed-request-'))
  const requestFile = path.join(requestRoot, 'request.json')
  try {
    fs.writeFileSync(requestFile, `${JSON.stringify({ schemaVersion: 1, outputPath, scene })}\n`, 'utf8')
    const run = spawnSync(hython, [generatorScript, requestFile], {
      encoding: 'utf8',
      maxBuffer: 16 * 1024 * 1024,
      windowsHide: true,
    })
    if (run.error) throw run.error
    if (run.status !== 0) {
      throw new Error(`Hython seed runner failed (${run.status}): ${(run.stderr || run.stdout || '').trim()}`)
    }
    const result = parseRunnerOutput(run.stdout)
    if (result.ok !== true) throw new Error('Hython seed runner returned ok=false')
    if (!sameExistingPath(result.outputPath, outputPath)) {
      throw new Error('Hython seed runner output path does not match the requested path')
    }
    requireObject(result.identity, 'Hython structural identity')
    return result
  } finally {
    fs.rmSync(requestRoot, { recursive: true, force: true })
  }
}

function sameExistingPath(left, right) {
  try {
    // Windows TEMP may use an 8.3 alias while the validated $HIP resolver
    // returns the long path. Compare canonical paths, not their spellings.
    return fs.realpathSync.native(path.resolve(left)) === fs.realpathSync.native(path.resolve(right))
  } catch {
    return false
  }
}

export function buildSeedFixtureManifest({
  input,
  hipRoot,
  generatorScript = defaultGeneratorScript,
  runnerResult,
}) {
  validateSeedGeneratorInput(input)
  const outputPath = resolveHipArtifactPath(input.output.hip, hipRoot)
  if (!fs.existsSync(outputPath) || !fs.statSync(outputPath).isFile() || fs.statSync(outputPath).size <= 0) {
    throw new Error(`generated seed HIP is missing or empty: ${outputPath}`)
  }
  if (!sameExistingPath(runnerResult.outputPath, outputPath)) {
    throw new Error('runner result does not point at the generated seed HIP')
  }
  const manifest = {
    schemaVersion: 1,
    fixtureId: input.fixtureId,
    capabilityFamily: input.capabilityFamily,
    instanceRole: input.instanceRole,
    generator: {
      id: 'dsh-houdini-generic-seed',
      version: input.generatorVersion,
      scriptSha256: sha256File(generatorScript),
      parametersSha256: seedParametersSha256(input),
      deterministic: true,
    },
    output: {
      hip: input.output.hip,
      sha256: sha256File(outputPath),
      identitySha256: sha256Json(runnerResult.identity),
      houdini: runnerResult.houdini,
    },
    evaluatorMaterialExposed: false,
  }
  validateSeedFixture(manifest, { hipRoot })
  return manifest
}

export function generateSeedFixture({
  input,
  hipRoot,
  hython,
  manifestFile,
  generatorScript = defaultGeneratorScript,
  overwrite = false,
  repeatCheck = true,
}) {
  validateSeedGeneratorInput(input)
  const resolvedHipRoot = path.resolve(hipRoot)
  const outputPath = resolveHipArtifactPath(input.output.hip, resolvedHipRoot)
  const resolvedManifest = path.resolve(manifestFile)
  if (!overwrite && fs.existsSync(outputPath)) throw new Error(`seed HIP already exists: ${outputPath}`)
  if (!overwrite && fs.existsSync(resolvedManifest)) throw new Error(`seed manifest already exists: ${resolvedManifest}`)

  const first = runSeedHython({ hython, generatorScript, outputPath, scene: input.scene })
  const firstIdentity = sha256Json(first.identity)
  if (repeatCheck) {
    const repeatRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-houdini-seed-repeat-'))
    try {
      const repeatOutput = resolveHipArtifactPath(input.output.hip, repeatRoot)
      const second = runSeedHython({ hython, generatorScript, outputPath: repeatOutput, scene: input.scene })
      const secondIdentity = sha256Json(second.identity)
      if (secondIdentity !== firstIdentity) {
        throw new Error(`seed structural identity is not deterministic: first=${firstIdentity} second=${secondIdentity}`)
      }
    } finally {
      fs.rmSync(repeatRoot, { recursive: true, force: true })
    }
  }

  const manifest = buildSeedFixtureManifest({
    input,
    hipRoot: resolvedHipRoot,
    generatorScript,
    runnerResult: first,
  })
  fs.mkdirSync(path.dirname(resolvedManifest), { recursive: true })
  fs.writeFileSync(resolvedManifest, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8')
  return {
    manifest,
    manifestSha256: sha256File(resolvedManifest),
    outputPath,
    manifestFile: resolvedManifest,
    repeatChecked: repeatCheck,
  }
}

function usage() {
  return [
    'usage: node tools/benchmark-seed.mjs generate <input.json>',
    '  --hip-root <dir> --hython <hython.exe> --manifest <output.json>',
    '  [--overwrite] [--skip-repeat-check]',
  ].join('\n')
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
if (isMain) {
  const [command, inputFile, ...options] = process.argv.slice(2)
  const option = (name) => {
    const index = options.indexOf(name)
    return index >= 0 ? options[index + 1] : undefined
  }
  if (command !== 'generate' || !inputFile || !option('--hip-root') || !option('--hython') || !option('--manifest')) {
    console.error(usage())
    process.exitCode = 2
  } else {
    try {
      const input = JSON.parse(fs.readFileSync(path.resolve(inputFile), 'utf8'))
      const summary = generateSeedFixture({
        input,
        hipRoot: option('--hip-root'),
        hython: path.resolve(option('--hython')),
        manifestFile: option('--manifest'),
        overwrite: options.includes('--overwrite'),
        repeatCheck: !options.includes('--skip-repeat-check'),
      })
      console.log(JSON.stringify(summary, null, 2))
    } catch (error) {
      console.error(error instanceof Error ? error.message : String(error))
      process.exitCode = 1
    }
  }
}
