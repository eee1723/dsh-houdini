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
const ANSWER_CATEGORIES = ['user-preference', 'asset-location', 'output-format', 'execution-constraint']
const CLAIM_LEVELS = ['none', 'local-regression', 'within-family', 'cross-domain']
const HIP_ARTIFACT = /^\$HIP(?:\/|$)/
const SCORE_LIMITS = Object.freeze({
  coreDelivery: 40,
  objectiveEvidence: 25,
  independentVisual: 25,
  honestDelivery: 10,
})

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

function requireStringArray(value, label, { minItems = 0 } = {}) {
  if (!Array.isArray(value) || value.length < minItems) {
    throw new Error(`${label} must be an array with at least ${minItems} item(s)`)
  }
  for (const [index, item] of value.entries()) requireString(item, `${label}[${index}]`)
  if (new Set(value).size !== value.length) throw new Error(`${label} must not contain duplicates`)
}

function requireHipArtifact(value, label) {
  requireString(value, label)
  if (!HIP_ARTIFACT.test(value)) throw new Error(`${label} must start with $HIP/`)
}

function requireEnum(value, choices, label) {
  if (!choices.includes(value)) throw new Error(`${label} must be one of: ${choices.join(', ')}`)
}

function requireBoolean(value, label) {
  if (typeof value !== 'boolean') throw new Error(`${label} must be a boolean`)
}

function requireNumber(value, label, minimum, maximum) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < minimum || value > maximum) {
    throw new Error(`${label} must be a finite number between ${minimum} and ${maximum}`)
  }
}

function requireSchemaVersion(manifest, label) {
  requireObject(manifest, label)
  if (manifest.schemaVersion !== 1) throw new Error(`${label} schemaVersion must be 1`)
}

function requireExactKeys(value, allowed, label) {
  const extras = Object.keys(value).filter((key) => !allowed.includes(key))
  if (extras.length) throw new Error(`${label} has unsupported field(s): ${extras.join(', ')}`)
}

export function validatePublicBrief(manifest) {
  requireSchemaVersion(manifest, 'public brief')
  requireExactKeys(manifest, [
    'schemaVersion', 'briefId', 'capabilityFamily', 'instanceRole', 'language',
    'agentMessage', 'resources', 'evaluatorMaterialExposed',
  ], 'public brief')
  requireString(manifest.briefId, 'briefId')
  requireEnum(manifest.capabilityFamily, FAMILIES, 'capabilityFamily')
  requireEnum(manifest.instanceRole, ROLES, 'instanceRole')
  requireString(manifest.language, 'language')
  requireString(manifest.agentMessage, 'agentMessage')
  if (manifest.evaluatorMaterialExposed !== false) throw new Error('public brief must not expose evaluator material')
  if (!Array.isArray(manifest.resources)) throw new Error('resources must be an array')
  const ids = new Set()
  const hashes = new Set()
  for (const [index, resource] of manifest.resources.entries()) {
    requireObject(resource, `resources[${index}]`)
    requireExactKeys(resource, ['resourceId', 'sha256', 'mediaType'], `resources[${index}]`)
    requireString(resource.resourceId, `resources[${index}].resourceId`)
    requireHash(resource.sha256, `resources[${index}].sha256`)
    requireString(resource.mediaType, `resources[${index}].mediaType`)
    if (ids.has(resource.resourceId)) throw new Error('resourceId values must be unique')
    if (hashes.has(resource.sha256)) throw new Error('resource sha256 values must be unique')
    ids.add(resource.resourceId)
    hashes.add(resource.sha256)
  }
  return manifest
}

/** Return the only public-brief fields that may enter the execution agent context. */
export function publicBriefAgentPayload(manifest) {
  validatePublicBrief(manifest)
  return {
    message: manifest.agentMessage,
    resources: manifest.resources.map((resource) => ({ ...resource })),
  }
}

export function validateAllowedAnswers(manifest, { publicBriefSha256 } = {}) {
  requireSchemaVersion(manifest, 'allowed answers')
  requireExactKeys(manifest, ['schemaVersion', 'answerSetId', 'publicBriefSha256', 'entries'], 'allowed answers')
  requireString(manifest.answerSetId, 'answerSetId')
  requireHash(manifest.publicBriefSha256, 'publicBriefSha256')
  if (publicBriefSha256 !== undefined && manifest.publicBriefSha256 !== publicBriefSha256) {
    throw new Error('allowed answers publicBriefSha256 does not match the sealed public brief')
  }
  if (!Array.isArray(manifest.entries)) throw new Error('entries must be an array')
  const keys = new Set()
  const patterns = new Set()
  for (const [index, entry] of manifest.entries.entries()) {
    requireObject(entry, `entries[${index}]`)
    requireExactKeys(entry, [
      'questionKey', 'questionPatternSha256', 'category', 'answer', 'maxUses',
      'containsImplementationGuidance', 'containsEvaluatorMaterial',
    ], `entries[${index}]`)
    requireString(entry.questionKey, `entries[${index}].questionKey`)
    requireHash(entry.questionPatternSha256, `entries[${index}].questionPatternSha256`)
    requireEnum(entry.category, ANSWER_CATEGORIES, `entries[${index}].category`)
    requireString(entry.answer, `entries[${index}].answer`)
    if (entry.maxUses !== 1) throw new Error(`entries[${index}].maxUses must be 1`)
    if (entry.containsImplementationGuidance !== false) {
      throw new Error(`entries[${index}] must not contain implementation guidance`)
    }
    if (entry.containsEvaluatorMaterial !== false) {
      throw new Error(`entries[${index}] must not contain evaluator material`)
    }
    if (keys.has(entry.questionKey)) throw new Error('questionKey values must be unique')
    if (patterns.has(entry.questionPatternSha256)) throw new Error('questionPatternSha256 values must be unique')
    keys.add(entry.questionKey)
    patterns.add(entry.questionPatternSha256)
  }
  return manifest
}

export function validateSeedFixtureManifest(manifest) {
  requireSchemaVersion(manifest, 'seed fixture')
  requireExactKeys(manifest, [
    'schemaVersion', 'fixtureId', 'capabilityFamily', 'instanceRole', 'generator',
    'output', 'evaluatorMaterialExposed',
  ], 'seed fixture')
  requireString(manifest.fixtureId, 'fixtureId')
  requireEnum(manifest.capabilityFamily, FAMILIES, 'capabilityFamily')
  requireEnum(manifest.instanceRole, ROLES, 'instanceRole')
  requireObject(manifest.generator, 'generator')
  requireExactKeys(manifest.generator, [
    'id', 'version', 'scriptSha256', 'parametersSha256', 'deterministic',
  ], 'generator')
  requireString(manifest.generator.id, 'generator.id')
  requireString(manifest.generator.version, 'generator.version')
  requireHash(manifest.generator.scriptSha256, 'generator.scriptSha256')
  requireHash(manifest.generator.parametersSha256, 'generator.parametersSha256')
  if (manifest.generator.deterministic !== true) throw new Error('generator.deterministic must be true')
  requireObject(manifest.output, 'output')
  requireExactKeys(manifest.output, ['hip', 'sha256', 'identitySha256', 'houdini'], 'output')
  requireHipArtifact(manifest.output.hip, 'output.hip')
  if (!/\.hip(?:lc|nc)?(?:\.gz)?$/i.test(manifest.output.hip)) {
    throw new Error('output.hip must name a .hip, .hiplc, or .hipnc scene file')
  }
  requireHash(manifest.output.sha256, 'output.sha256')
  requireHash(manifest.output.identitySha256, 'output.identitySha256')
  requireString(manifest.output.houdini, 'output.houdini')
  if (manifest.evaluatorMaterialExposed !== false) throw new Error('seed fixture must not expose evaluator material')
  return manifest
}

export function validateSeedFixture(manifest, { hipRoot } = {}) {
  validateSeedFixtureManifest(manifest)
  requireString(hipRoot, 'hipRoot')
  const output = requireNonemptyFile(resolveHipArtifactPath(manifest.output.hip, hipRoot), 'seed HIP')
  const actualSha256 = sha256File(output.path)
  if (actualSha256 !== manifest.output.sha256) throw new Error('seed HIP sha256 does not match fixture manifest')
  return { ...output, sha256: actualSha256, fixtureId: manifest.fixtureId }
}

export function validateEvaluatorSpec(manifest, { publicBriefSha256 } = {}) {
  requireSchemaVersion(manifest, 'evaluator spec')
  requireExactKeys(manifest, [
    'schemaVersion', 'specId', 'capabilityFamily', 'instanceRole', 'publicBriefSha256',
    'criteria', 'hardFailures', 'scoreThreshold', 'evaluatorMaterialExposed',
  ], 'evaluator spec')
  requireString(manifest.specId, 'specId')
  requireEnum(manifest.capabilityFamily, FAMILIES, 'capabilityFamily')
  requireEnum(manifest.instanceRole, ROLES, 'instanceRole')
  requireHash(manifest.publicBriefSha256, 'publicBriefSha256')
  if (publicBriefSha256 !== undefined && manifest.publicBriefSha256 !== publicBriefSha256) {
    throw new Error('evaluator spec publicBriefSha256 does not match the public brief file')
  }
  if (!Array.isArray(manifest.criteria) || manifest.criteria.length < 4) {
    throw new Error('criteria must contain at least four items')
  }
  const criterionIds = new Set()
  const dimensionTotals = Object.fromEntries(Object.keys(SCORE_LIMITS).map((key) => [key, 0]))
  for (const [index, criterion] of manifest.criteria.entries()) {
    requireObject(criterion, `criteria[${index}]`)
    requireExactKeys(criterion, [
      'criterionId', 'dimension', 'maxPoints', 'requirement', 'evidence', 'critical',
    ], `criteria[${index}]`)
    requireString(criterion.criterionId, `criteria[${index}].criterionId`)
    if (criterionIds.has(criterion.criterionId)) throw new Error('criterionId values must be unique')
    criterionIds.add(criterion.criterionId)
    requireEnum(criterion.dimension, Object.keys(SCORE_LIMITS), `criteria[${index}].dimension`)
    requireNumber(criterion.maxPoints, `criteria[${index}].maxPoints`, Number.MIN_VALUE, SCORE_LIMITS[criterion.dimension])
    requireString(criterion.requirement, `criteria[${index}].requirement`)
    requireStringArray(criterion.evidence, `criteria[${index}].evidence`, { minItems: 1 })
    for (const [evidenceIndex, evidence] of criterion.evidence.entries()) {
      requireEnum(evidence, ['deterministic', 'blind-visual', 'target-visual', 'trace', 'human'], `criteria[${index}].evidence[${evidenceIndex}]`)
    }
    requireBoolean(criterion.critical, `criteria[${index}].critical`)
    dimensionTotals[criterion.dimension] += criterion.maxPoints
  }
  for (const [dimension, expected] of Object.entries(SCORE_LIMITS)) {
    if (Math.abs(dimensionTotals[dimension] - expected) > 1e-9) {
      throw new Error(`${dimension} criteria must total exactly ${expected} points`)
    }
  }
  if (!Array.isArray(manifest.hardFailures)) throw new Error('hardFailures must be an array')
  const failureIds = new Set()
  const criteriaById = new Map(manifest.criteria.map((item) => [item.criterionId, item]))
  for (const [index, failure] of manifest.hardFailures.entries()) {
    requireObject(failure, `hardFailures[${index}]`)
    requireExactKeys(failure, ['failureId', 'criterionId', 'condition'], `hardFailures[${index}]`)
    requireString(failure.failureId, `hardFailures[${index}].failureId`)
    requireString(failure.criterionId, `hardFailures[${index}].criterionId`)
    requireString(failure.condition, `hardFailures[${index}].condition`)
    if (failureIds.has(failure.failureId)) throw new Error('failureId values must be unique')
    failureIds.add(failure.failureId)
    const criterion = criteriaById.get(failure.criterionId)
    if (!criterion) throw new Error(`hard failure references unknown criterionId: ${failure.criterionId}`)
    if (criterion.critical !== true) throw new Error(`hard failure criterion must be critical: ${failure.criterionId}`)
  }
  if (manifest.scoreThreshold !== 75) throw new Error('scoreThreshold must be 75')
  if (manifest.evaluatorMaterialExposed !== false) throw new Error('evaluator material must not be exposed to the execution agent')
  return manifest
}

export function validateSealedInstanceManifest(manifest) {
  requireSchemaVersion(manifest, 'sealed instance manifest')
  requireExactKeys(manifest, [
    'schemaVersion', 'instanceId', 'capabilityFamily', 'instanceRole', 'files',
    'releasePolicy', 'evaluatorMaterialExposed',
  ], 'sealed instance manifest')
  requireString(manifest.instanceId, 'instanceId')
  requireEnum(manifest.capabilityFamily, FAMILIES, 'capabilityFamily')
  requireEnum(manifest.instanceRole, ROLES, 'instanceRole')
  requireObject(manifest.files, 'files')
  requireExactKeys(manifest.files, [
    'publicBriefSha256', 'allowedAnswersSha256', 'seedFixtureSha256',
    'evaluatorSpecSha256', 'resourceSha256',
  ], 'files')
  for (const field of ['publicBriefSha256', 'allowedAnswersSha256', 'seedFixtureSha256', 'evaluatorSpecSha256']) {
    requireHash(manifest.files[field], `files.${field}`)
  }
  requireStringArray(manifest.files.resourceSha256, 'files.resourceSha256')
  for (const [index, hash] of manifest.files.resourceSha256.entries()) requireHash(hash, `files.resourceSha256[${index}]`)
  requireObject(manifest.releasePolicy, 'releasePolicy')
  requireExactKeys(manifest.releasePolicy, [
    'productionSurfaceCommit', 'revealAfterSurfaceFreeze', 'becomesCalibrationAfterReveal',
  ], 'releasePolicy')
  requireHash(manifest.releasePolicy.productionSurfaceCommit, 'releasePolicy.productionSurfaceCommit', GIT_SHA)
  if (manifest.releasePolicy.revealAfterSurfaceFreeze !== true) throw new Error('revealAfterSurfaceFreeze must be true')
  if (manifest.releasePolicy.becomesCalibrationAfterReveal !== true) throw new Error('becomesCalibrationAfterReveal must be true')
  if (manifest.evaluatorMaterialExposed !== false) throw new Error('sealed evaluator material must not be exposed')
  return manifest
}

export function validateEvaluationResult(manifest, { runManifest } = {}) {
  requireSchemaVersion(manifest, 'evaluation result')
  requireExactKeys(manifest, [
    'schemaVersion', 'runId', 'evaluatorSpecSha256', 'inputs', 'hardFailures',
    'scores', 'total', 'hardFailure', 'coreSuccess', 'claimLevel',
    'blindResultSha256', 'targetResultSha256', 'humanReviewSha256',
  ], 'evaluation result')
  requireString(manifest.runId, 'runId')
  requireHash(manifest.evaluatorSpecSha256, 'evaluatorSpecSha256')
  requireObject(manifest.inputs, 'inputs')
  requireExactKeys(manifest.inputs, [
    'deterministicEvidenceSha256', 'blindVisualInputSha256', 'targetInputSha256',
  ], 'inputs')
  for (const field of ['deterministicEvidenceSha256', 'blindVisualInputSha256', 'targetInputSha256']) {
    requireHash(manifest.inputs[field], `inputs.${field}`)
  }
  if (manifest.inputs.blindVisualInputSha256 === manifest.inputs.targetInputSha256) {
    throw new Error('blind visual and target verification inputs must be independently sealed')
  }
  requireStringArray(manifest.hardFailures, 'hardFailures')
  requireObject(manifest.scores, 'scores')
  requireExactKeys(manifest.scores, [
    'coreDelivery', 'objectiveEvidence', 'independentVisual', 'honestDelivery',
  ], 'scores')
  const scoreLimits = {
    coreDelivery: 40,
    objectiveEvidence: 25,
    independentVisual: 25,
    honestDelivery: 10,
  }
  for (const [field, maximum] of Object.entries(scoreLimits)) {
    requireNumber(manifest.scores[field], `scores.${field}`, 0, maximum)
  }
  requireNumber(manifest.total, 'total', 0, 100)
  const expectedTotal = Object.keys(scoreLimits).reduce((sum, field) => sum + manifest.scores[field], 0)
  if (Math.abs(manifest.total - expectedTotal) > 1e-9) throw new Error('total must equal the four dimension scores')
  requireBoolean(manifest.hardFailure, 'hardFailure')
  requireBoolean(manifest.coreSuccess, 'coreSuccess')
  const expectedHardFailure = manifest.hardFailures.length > 0
  if (manifest.hardFailure !== expectedHardFailure) throw new Error('hardFailure must match whether hardFailures is non-empty')
  const expectedCoreSuccess = !manifest.hardFailure && manifest.total >= 75
  if (manifest.coreSuccess !== expectedCoreSuccess) throw new Error('coreSuccess must mean no hard failure and total >= 75')
  requireEnum(manifest.claimLevel, CLAIM_LEVELS, 'claimLevel')
  if (!manifest.coreSuccess && manifest.claimLevel !== 'none') throw new Error('an unsuccessful run cannot claim capability improvement')
  for (const field of ['blindResultSha256', 'targetResultSha256']) requireHash(manifest[field], field)
  if (manifest.humanReviewSha256 !== undefined) requireHash(manifest.humanReviewSha256, 'humanReviewSha256')

  if (runManifest !== undefined) {
    validateRunManifest(runManifest)
    if (runManifest.status === 'running') throw new Error('evaluation requires a terminal run manifest')
    if (manifest.runId !== runManifest.runId) throw new Error('evaluation runId does not match run manifest')
    if (manifest.evaluatorSpecSha256 !== runManifest.evaluatorSpecSha256) {
      throw new Error('evaluation evaluatorSpecSha256 does not match run manifest')
    }
    if (runManifest.evaluation?.blindResultSha256 !== undefined
        && manifest.blindResultSha256 !== runManifest.evaluation.blindResultSha256) {
      throw new Error('blindResultSha256 does not match run manifest')
    }
    if (runManifest.evaluation?.targetResultSha256 !== undefined
        && manifest.targetResultSha256 !== runManifest.evaluation.targetResultSha256) {
      throw new Error('targetResultSha256 does not match run manifest')
    }
    if (runManifest.evaluation !== undefined) {
      if (manifest.hardFailure !== runManifest.evaluation.hardFailure) {
        throw new Error('hardFailure does not match run manifest')
      }
      if (manifest.total !== runManifest.evaluation.score) throw new Error('total does not match run manifest score')
      if (manifest.claimLevel !== runManifest.evaluation.claimLevel) {
        throw new Error('claimLevel does not match run manifest')
      }
    }
  }
  return manifest
}

export function validateRunInputs({
  runManifest,
  publicBrief,
  publicBriefSha256,
  allowedAnswers,
  allowedAnswersSha256,
  seedFixture,
  hipRoot,
}) {
  validateRunManifest(runManifest)
  validatePublicBrief(publicBrief)
  requireHash(publicBriefSha256, 'publicBriefSha256')
  validateAllowedAnswers(allowedAnswers, { publicBriefSha256 })
  requireHash(allowedAnswersSha256, 'allowedAnswersSha256')
  const seed = validateSeedFixture(seedFixture, { hipRoot })

  for (const [label, value] of [['public brief', publicBrief], ['seed fixture', seedFixture]]) {
    if (value.capabilityFamily !== runManifest.capabilityFamily) {
      throw new Error(`${label} capabilityFamily does not match run manifest`)
    }
    if (value.instanceRole !== runManifest.instanceRole) {
      throw new Error(`${label} instanceRole does not match run manifest`)
    }
  }
  if (runManifest.agentExposure.publicBriefSha256 !== publicBriefSha256) {
    throw new Error('run publicBriefSha256 does not match public brief file')
  }
  if (runManifest.agentExposure.allowedAnswersSha256 !== allowedAnswersSha256) {
    throw new Error('run allowedAnswersSha256 does not match allowed answers file')
  }
  if (runManifest.agentExposure.seedSceneSha256 !== seedFixture.output.sha256) {
    throw new Error('run seedSceneSha256 does not match seed HIP')
  }
  const declaredResources = [...runManifest.agentExposure.resourceSha256].sort()
  const briefResources = publicBrief.resources.map((resource) => resource.sha256).sort()
  if (JSON.stringify(declaredResources) !== JSON.stringify(briefResources)) {
    throw new Error('run resourceSha256 does not exactly match public brief resources')
  }
  return {
    runId: runManifest.runId,
    publicBriefSha256,
    allowedAnswersSha256,
    seedSceneSha256: seed.sha256,
    resourceSha256: briefResources,
  }
}

export function validateProtocolManifest(manifest) {
  requireObject(manifest, 'protocol manifest')
  requireExactKeys(manifest, [
    'schemaVersion', 'protocolVersion', 'createdAt', 'baselineCommit',
    'agentSurfaceSha256', 'environment', 'execution', 'evaluation', 'sealedInstances',
  ], 'protocol manifest')
  if (manifest.schemaVersion !== 1) throw new Error('protocol schemaVersion must be 1')
  requireString(manifest.protocolVersion, 'protocolVersion')
  requireDateTime(manifest.createdAt, 'createdAt')
  requireHash(manifest.baselineCommit, 'baselineCommit', GIT_SHA)
  requireHash(manifest.agentSurfaceSha256, 'agentSurfaceSha256')
  requireObject(manifest.environment, 'environment')
  requireExactKeys(manifest.environment, ['houdini', 'dsh', 'plugin', 'visionToolkit'], 'environment')
  for (const field of ['houdini', 'dsh', 'plugin', 'visionToolkit']) {
    requireString(manifest.environment[field], `environment.${field}`)
  }
  requireObject(manifest.execution, 'execution')
  requireExactKeys(manifest.execution, ['models', 'budget', 'additionalCorrectionLimit'], 'execution')
  if (!Array.isArray(manifest.execution.models) || manifest.execution.models.length !== 2 || new Set(manifest.execution.models).size !== 2) {
    throw new Error('execution.models must contain exactly two distinct model identifiers')
  }
  for (const [index, model] of manifest.execution.models.entries()) requireString(model, `execution.models[${index}]`)
  requireObject(manifest.execution.budget, 'execution.budget')
  requireExactKeys(manifest.execution.budget, ['wallMinutes', 'maxTurns'], 'execution.budget')
  requirePositiveInteger(manifest.execution.budget.wallMinutes, 'execution.budget.wallMinutes')
  requirePositiveInteger(manifest.execution.budget.maxTurns, 'execution.budget.maxTurns')
  if (manifest.execution.additionalCorrectionLimit !== 0) throw new Error('additionalCorrectionLimit must be 0')
  requireObject(manifest.evaluation, 'evaluation')
  requireExactKeys(manifest.evaluation, [
    'deterministicEvaluator', 'blindVisualEvaluator', 'targetEvaluator',
    'blindPromptSha256', 'targetPromptSha256',
  ], 'evaluation')
  for (const field of ['deterministicEvaluator', 'blindVisualEvaluator', 'targetEvaluator']) {
    requireString(manifest.evaluation[field], `evaluation.${field}`)
  }
  requireHash(manifest.evaluation.blindPromptSha256, 'evaluation.blindPromptSha256')
  requireHash(manifest.evaluation.targetPromptSha256, 'evaluation.targetPromptSha256')
  if (manifest.evaluation.blindPromptSha256 === manifest.evaluation.targetPromptSha256) {
    throw new Error('blind and target evaluator prompts must be independently sealed')
  }
  requireObject(manifest.sealedInstances, 'sealedInstances')
  requireExactKeys(manifest.sealedInstances, FAMILIES, 'sealedInstances')
  for (const family of FAMILIES) {
    requireObject(manifest.sealedInstances[family], `sealedInstances.${family}`)
    requireExactKeys(manifest.sealedInstances[family], ROLES, `sealedInstances.${family}`)
    for (const role of ROLES) requireHash(manifest.sealedInstances[family][role], `sealedInstances.${family}.${role}`)
  }
  return manifest
}

export function validateRunManifest(manifest) {
  requireObject(manifest, 'run manifest')
  requireExactKeys(manifest, [
    'schemaVersion', 'runId', 'protocolVersion', 'protocolManifestSha256',
    'baselineCommit', 'agentSurfaceSha256', 'phase', 'capabilityFamily',
    'instanceRole', 'model', 'instanceSealedSha256', 'evaluatorSpecSha256',
    'agentExposure', 'startedAt', 'finishedAt', 'status', 'terminationReason',
    'evidence', 'evaluation',
  ], 'run manifest')
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
  requireExactKeys(manifest.agentExposure, [
    'publicBriefSha256', 'allowedAnswersSha256', 'seedSceneSha256',
    'resourceSha256', 'evaluatorMaterialExposed',
  ], 'agentExposure')
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
  if (manifest.terminationReason !== undefined) requireString(manifest.terminationReason, 'terminationReason')
  if (manifest.finishedAt !== undefined) {
    requireDateTime(manifest.finishedAt, 'finishedAt')
    if (Date.parse(manifest.finishedAt) < Date.parse(manifest.startedAt)) {
      throw new Error('finishedAt must not be earlier than startedAt')
    }
  }
  const terminal = manifest.status !== 'running'
  if (terminal && manifest.finishedAt === undefined) throw new Error('terminal run requires finishedAt')
  if (terminal && manifest.terminationReason === undefined) throw new Error('terminal run requires terminationReason')
  if (!terminal && manifest.finishedAt !== undefined) throw new Error('running run must not have finishedAt')
  if (manifest.evidence !== undefined) {
    requireObject(manifest.evidence, 'evidence')
    requireExactKeys(manifest.evidence, ['trace', 'hip', 'cache', 'render', 'finalNodes'], 'evidence')
    if (manifest.evidence.trace !== undefined) requireString(manifest.evidence.trace, 'evidence.trace')
    if (manifest.evidence.hip !== undefined) requireHipArtifact(manifest.evidence.hip, 'evidence.hip')
    for (const field of ['cache', 'render']) {
      if (manifest.evidence[field] === undefined) continue
      requireStringArray(manifest.evidence[field], `evidence.${field}`)
      for (const [index, value] of manifest.evidence[field].entries()) {
        requireHipArtifact(value, `evidence.${field}[${index}]`)
      }
    }
    if (manifest.evidence.finalNodes !== undefined) {
      requireStringArray(manifest.evidence.finalNodes, 'evidence.finalNodes')
      for (const [index, value] of manifest.evidence.finalNodes.entries()) {
        if (!value.startsWith('/')) throw new Error(`evidence.finalNodes[${index}] must be an absolute Houdini node path`)
      }
    }
  }
  if (manifest.evaluation !== undefined) {
    if (!terminal) throw new Error('running run must not have evaluation')
    requireObject(manifest.evaluation, 'evaluation')
    requireExactKeys(manifest.evaluation, [
      'hardFailure', 'score', 'claimLevel', 'blindResultSha256', 'targetResultSha256',
    ], 'evaluation')
    requireBoolean(manifest.evaluation.hardFailure, 'evaluation.hardFailure')
    requireNumber(manifest.evaluation.score, 'evaluation.score', 0, 100)
    requireEnum(manifest.evaluation.claimLevel, CLAIM_LEVELS, 'evaluation.claimLevel')
    for (const field of ['blindResultSha256', 'targetResultSha256']) {
      if (manifest.evaluation[field] !== undefined) requireHash(manifest.evaluation[field], `evaluation.${field}`)
    }
  }
  return manifest
}

function inside(root, candidate) {
  const relative = path.relative(root, candidate)
  return relative === '' || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative))
}

function realpathIfPresent(value) {
  return fs.existsSync(value) ? fs.realpathSync.native(value) : path.resolve(value)
}

export function resolveHipArtifactPath(value, hipRoot) {
  requireHipArtifact(value, 'artifact path')
  if (value === '$HIP') throw new Error('artifact path must name a file below $HIP, not the $HIP directory itself')
  const root = realpathIfPresent(path.resolve(hipRoot))
  const candidate = path.resolve(root, ...value.slice('$HIP/'.length).split('/'))
  if (!inside(root, candidate)) throw new Error(`artifact path escapes $HIP: ${value}`)
  const resolved = realpathIfPresent(candidate)
  if (!inside(root, resolved)) throw new Error(`artifact symlink escapes $HIP: ${value}`)
  return resolved
}

function requireNonemptyFile(file, label) {
  if (!fs.existsSync(file)) throw new Error(`${label} does not exist: ${file}`)
  const stat = fs.statSync(file)
  if (!stat.isFile()) throw new Error(`${label} must be a file: ${file}`)
  if (stat.size <= 0) throw new Error(`${label} must not be empty: ${file}`)
  return { path: file, bytes: stat.size, mtimeMs: stat.mtimeMs }
}

/** Validate a completed non-scoring smoke run against its real artifact roots. */
export function validateSmokeRun(manifest, {
  hipRoot,
  repositoryRoot = defaultRoot,
} = {}) {
  validateRunManifest(manifest)
  if (manifest.phase !== 'smoke') throw new Error('smoke fixture validation requires phase="smoke"')
  if (manifest.status !== 'completed') throw new Error('smoke fixture validation requires status="completed"')
  if (!manifest.finishedAt) throw new Error('completed smoke requires finishedAt')
  requireString(hipRoot, 'hipRoot')
  requireObject(manifest.evidence, 'completed smoke evidence')
  const evidence = manifest.evidence
  requireString(evidence.trace, 'evidence.trace')
  requireHipArtifact(evidence.hip, 'evidence.hip')
  requireStringArray(evidence.render, 'evidence.render', { minItems: 1 })
  requireStringArray(evidence.finalNodes, 'evidence.finalNodes', { minItems: 1 })

  if (!path.isAbsolute(evidence.trace)) throw new Error('evidence.trace must be an absolute path')
  const tracePath = realpathIfPresent(evidence.trace)
  const repoPath = realpathIfPresent(path.resolve(repositoryRoot))
  if (inside(repoPath, tracePath)) throw new Error('evidence.trace must stay outside the plugin repository')

  if (!/\.hip(?:lc|nc)?(?:\.gz)?$/i.test(evidence.hip)) {
    throw new Error('evidence.hip must name a .hip, .hiplc, or .hipnc scene file')
  }
  const hip = requireNonemptyFile(resolveHipArtifactPath(evidence.hip, hipRoot), 'HIP artifact')
  const cache = (evidence.cache || []).map((value, index) => (
    requireNonemptyFile(resolveHipArtifactPath(value, hipRoot), `cache artifact ${index + 1}`)
  ))
  const render = evidence.render.map((value, index) => (
    requireNonemptyFile(resolveHipArtifactPath(value, hipRoot), `render artifact ${index + 1}`)
  ))
  const trace = requireNonemptyFile(tracePath, 'trace artifact')

  return {
    runId: manifest.runId,
    capabilityFamily: manifest.capabilityFamily,
    hip,
    cache,
    render,
    trace,
    finalNodes: [...evidence.finalNodes],
  }
}

function loadJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'))
}

function usage() {
  return [
    'usage: node tools/benchmark-manifest.mjs surface-hash [repo] | seal <file>',
    '  validate-protocol <file> | validate-run <file> | validate-brief <file>',
    '  validate-answers <file> [--brief-sha <sha256>]',
    '  validate-seed <file> --hip-root <dir>',
    '  validate-evaluator-spec <file> [--brief-sha <sha256>]',
    '  validate-instance <file>',
    '  validate-inputs <run.json> --brief <file> --answers <file> --seed <file> --hip-root <dir>',
    '  validate-evaluation <file> --run <run.json>',
    '  validate-smoke <run.json> --hip-root <dir> [--repo-root <dir>]',
  ].join('\n')
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
if (isMain) {
  const [command, argument, ...options] = process.argv.slice(2)
  const option = (name) => {
    const index = options.indexOf(name)
    return index >= 0 ? options[index + 1] : undefined
  }
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
  } else if (command === 'validate-brief' && argument) {
    validatePublicBrief(loadJson(path.resolve(argument)))
    console.log('public brief valid')
  } else if (command === 'validate-answers' && argument) {
    validateAllowedAnswers(loadJson(path.resolve(argument)), { publicBriefSha256: option('--brief-sha') })
    console.log('allowed answers valid')
  } else if (command === 'validate-seed' && argument) {
    const summary = validateSeedFixture(loadJson(path.resolve(argument)), { hipRoot: option('--hip-root') })
    console.log(JSON.stringify(summary, null, 2))
  } else if (command === 'validate-evaluator-spec' && argument) {
    validateEvaluatorSpec(loadJson(path.resolve(argument)), { publicBriefSha256: option('--brief-sha') })
    console.log('evaluator spec valid')
  } else if (command === 'validate-instance' && argument) {
    validateSealedInstanceManifest(loadJson(path.resolve(argument)))
    console.log('sealed instance manifest valid')
  } else if (command === 'validate-inputs' && argument
      && option('--brief') && option('--answers') && option('--seed')) {
    const briefFile = path.resolve(option('--brief'))
    const answersFile = path.resolve(option('--answers'))
    const summary = validateRunInputs({
      runManifest: loadJson(path.resolve(argument)),
      publicBrief: loadJson(briefFile),
      publicBriefSha256: sha256File(briefFile),
      allowedAnswers: loadJson(answersFile),
      allowedAnswersSha256: sha256File(answersFile),
      seedFixture: loadJson(path.resolve(option('--seed'))),
      hipRoot: option('--hip-root'),
    })
    console.log(JSON.stringify(summary, null, 2))
  } else if (command === 'validate-evaluation' && argument && option('--run')) {
    validateEvaluationResult(loadJson(path.resolve(argument)), {
      runManifest: loadJson(path.resolve(option('--run'))),
    })
    console.log('evaluation result valid')
  } else if (command === 'validate-smoke' && argument) {
    const summary = validateSmokeRun(loadJson(path.resolve(argument)), {
      hipRoot: option('--hip-root'),
      repositoryRoot: option('--repo-root') || defaultRoot,
    })
    console.log(JSON.stringify(summary, null, 2))
  } else {
    console.error(usage())
    process.exitCode = 2
  }
}
