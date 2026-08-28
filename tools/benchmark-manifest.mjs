import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const defaultRoot = path.dirname(here)

export const AGENT_SURFACE_ENTRIES = Object.freeze([
  'client.js',
  'docs/tool-design.md',
  'presets',
  'skills',
  'src',
])

const SHA256 = /^[0-9a-f]{64}$/
const GIT_SHA = /^[0-9a-f]{40}$/
const FAMILIES = ['mechanical', 'simulation', 'lookdev']
const ROLES = ['calibration', 'holdout', 'counterexample']
const PHASES = ['smoke', 'discovery', 'regression', 'generalization']
const STATUSES = ['running', 'completed', 'failed', 'invalidated']

function walkFiles(absolute, root) {
  const stat = fs.statSync(absolute)
  if (stat.isFile()) return [path.relative(root, absolute).replaceAll('\\', '/')]
  return fs.readdirSync(absolute, { withFileTypes: true }).flatMap((entry) => {
    const child = path.join(absolute, entry.name)
    return entry.isDirectory() ? walkFiles(child, root) : [path.relative(root, child).replaceAll('\\', '/')]
  })
}

export function listAgentSurfaceFiles(root = defaultRoot) {
  return AGENT_SURFACE_ENTRIES
    .flatMap((entry) => walkFiles(path.join(root, entry), root))
    .filter((file) => /\.(?:js|mjs|ts|md|ya?ml)$/.test(file))
    .filter((file) => !file.endsWith('generated-verb-contract.ts'))
    .sort()
}

export function sha256Bytes(value) {
  return crypto.createHash('sha256').update(value).digest('hex')
}

export function sha256File(file) {
  return sha256Bytes(fs.readFileSync(file))
}

export function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`
  }
  return JSON.stringify(value)
}

export function sha256Json(value) {
  return sha256Bytes(canonicalJson(value))
}

export function agentSurfaceHash(root = defaultRoot) {
  const hash = crypto.createHash('sha256')
  for (const relative of listAgentSurfaceFiles(root)) {
    const text = fs.readFileSync(path.join(root, relative), 'utf8').replaceAll('\r\n', '\n')
    hash.update(relative)
    hash.update('\0')
    hash.update(text)
    hash.update('\0')
  }
  return hash.digest('hex')
}

function requireObject(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${label} must be an object`)
}

function requireString(value, label) {
  if (typeof value !== 'string' || value.length === 0) throw new Error(`${label} must be a non-empty string`)
}

function requireHash(value, label, pattern = SHA256) {
  if (typeof value !== 'string' || !pattern.test(value)) throw new Error(`${label} must be a lowercase hexadecimal hash`)
}

function requirePositiveInteger(value, label) {
  if (!Number.isInteger(value) || value < 1) throw new Error(`${label} must be a positive integer`)
}

function requireDateTime(value, label) {
  requireString(value, label)
  if (Number.isNaN(Date.parse(value))) throw new Error(`${label} must be an ISO date-time`)
}

export function validateProtocolManifest(manifest) {
  requireObject(manifest, 'protocol manifest')
  if (manifest.schemaVersion !== 1) throw new Error('protocol schemaVersion must be 1')
  requireString(manifest.protocolVersion, 'protocolVersion')
  requireDateTime(manifest.createdAt, 'createdAt')
  requireHash(manifest.baselineCommit, 'baselineCommit', GIT_SHA)
  requireHash(manifest.agentSurfaceSha256, 'agentSurfaceSha256')
  requireObject(manifest.environment, 'environment')
  for (const field of ['houdini', 'dsh', 'plugin', 'visionToolkit']) {
    requireString(manifest.environment[field], `environment.${field}`)
  }
  requireObject(manifest.execution, 'execution')
  if (!Array.isArray(manifest.execution.models) || manifest.execution.models.length !== 2 || new Set(manifest.execution.models).size !== 2) {
    throw new Error('execution.models must contain exactly two distinct model identifiers')
  }
  for (const [index, model] of manifest.execution.models.entries()) requireString(model, `execution.models[${index}]`)
  requireObject(manifest.execution.budget, 'execution.budget')
  requirePositiveInteger(manifest.execution.budget.wallMinutes, 'execution.budget.wallMinutes')
  requirePositiveInteger(manifest.execution.budget.maxTurns, 'execution.budget.maxTurns')
  if (manifest.execution.additionalCorrectionLimit !== 0) throw new Error('additionalCorrectionLimit must be 0')
  requireObject(manifest.evaluation, 'evaluation')
  for (const field of ['deterministicEvaluator', 'blindVisualEvaluator', 'targetEvaluator']) {
    requireString(manifest.evaluation[field], `evaluation.${field}`)
  }
  requireHash(manifest.evaluation.blindPromptSha256, 'evaluation.blindPromptSha256')
  requireHash(manifest.evaluation.targetPromptSha256, 'evaluation.targetPromptSha256')
  requireObject(manifest.sealedInstances, 'sealedInstances')
  for (const family of FAMILIES) {
    requireObject(manifest.sealedInstances[family], `sealedInstances.${family}`)
    for (const role of ROLES) requireHash(manifest.sealedInstances[family][role], `sealedInstances.${family}.${role}`)
  }
  return manifest
}

export function validateRunManifest(manifest) {
  requireObject(manifest, 'run manifest')
  if (manifest.schemaVersion !== 1) throw new Error('run schemaVersion must be 1')
  requireString(manifest.runId, 'runId')
  requireString(manifest.protocolVersion, 'protocolVersion')
  requireHash(manifest.protocolManifestSha256, 'protocolManifestSha256')
  requireHash(manifest.baselineCommit, 'baselineCommit', GIT_SHA)
  requireHash(manifest.agentSurfaceSha256, 'agentSurfaceSha256')
  if (!PHASES.includes(manifest.phase)) throw new Error('phase is invalid')
  if (!FAMILIES.includes(manifest.capabilityFamily)) throw new Error('capabilityFamily is invalid')
  if (!ROLES.includes(manifest.instanceRole)) throw new Error('instanceRole is invalid')
  requireString(manifest.model, 'model')
  requireHash(manifest.instanceSealedSha256, 'instanceSealedSha256')
  requireHash(manifest.evaluatorSpecSha256, 'evaluatorSpecSha256')
  requireObject(manifest.agentExposure, 'agentExposure')
  for (const field of ['publicBriefSha256', 'allowedAnswersSha256', 'seedSceneSha256']) {
    requireHash(manifest.agentExposure[field], `agentExposure.${field}`)
  }
  if (!Array.isArray(manifest.agentExposure.resourceSha256)) throw new Error('agentExposure.resourceSha256 must be an array')
  for (const [index, hash] of manifest.agentExposure.resourceSha256.entries()) {
    requireHash(hash, `agentExposure.resourceSha256[${index}]`)
  }
  if (manifest.agentExposure.evaluatorMaterialExposed !== false) {
    throw new Error('agentExposure.evaluatorMaterialExposed must be false; invalidate contaminated runs')
  }
  requireDateTime(manifest.startedAt, 'startedAt')
  if (!STATUSES.includes(manifest.status)) throw new Error('status is invalid')
  return manifest
}

function loadJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'))
}

function usage() {
  return 'usage: node tools/benchmark-manifest.mjs surface-hash [repo] | seal <file> | validate-protocol <file> | validate-run <file>'
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
if (isMain) {
  const [command, argument] = process.argv.slice(2)
  if (command === 'surface-hash') {
    console.log(agentSurfaceHash(argument ? path.resolve(argument) : defaultRoot))
  } else if (command === 'seal' && argument) {
    console.log(sha256File(path.resolve(argument)))
  } else if (command === 'validate-protocol' && argument) {
    validateProtocolManifest(loadJson(path.resolve(argument)))
    console.log('protocol manifest valid')
  } else if (command === 'validate-run' && argument) {
    validateRunManifest(loadJson(path.resolve(argument)))
    console.log('run manifest valid')
  } else {
    console.error(usage())
    process.exitCode = 2
  }
}
