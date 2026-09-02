import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const BLIND_KEYS = ['schemaVersion', 'stage', 'observations', 'crossImageConsistency', 'limitations']
const BLIND_OBSERVATION_KEYS = ['evidenceId', 'visibleSubjects', 'geometry', 'materialColor', 'lighting', 'composition', 'defects', 'uncertainty']
const TARGET_KEYS = ['schemaVersion', 'stage', 'criteria', 'overall']
const TARGET_CRITERION_KEYS = ['criterionId', 'status', 'confidence', 'evidenceIds', 'deterministicEvidenceIds', 'rationale', 'uncertainty']
const HARD_FAILURE_RULE_KEYS = ['criterionId', 'reason']
const TARGET_OVERALL_KEYS = ['coreGoalStatus', 'visualStatus', 'conflicts', 'limitations']

function requireObject(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${label} must be an object`)
}

function requireExactKeys(value, keys, label) {
  const actual = Object.keys(value).sort()
  const expected = [...keys].sort()
  if (JSON.stringify(actual) !== JSON.stringify(expected)) throw new Error(`${label} fields are invalid: ${actual.join(', ')}`)
}

function requireAllowedKeys(value, required, optional, label) {
  const actual = Object.keys(value)
  const missing = required.filter((key) => !(key in value))
  const unsupported = actual.filter((key) => !required.includes(key) && !optional.includes(key))
  if (missing.length || unsupported.length) throw new Error(`${label} fields are invalid: missing=${missing.join(', ')} unsupported=${unsupported.join(', ')}`)
}

function requireStringArray(value, label) {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) throw new Error(`${label} must be a string array`)
}

function requireUniqueIds(value, label, { minItems = 0 } = {}) {
  requireStringArray(value, label)
  if (value.length < minItems || value.some((item) => !item)) throw new Error(`${label} must contain at least ${minItems} non-empty id(s)`)
  if (new Set(value).size !== value.length) throw new Error(`${label} must contain unique ids`)
  return new Set(value)
}

function requireExactIdSet(actual, expected, label) {
  const actualSorted = [...actual].sort()
  const expectedSorted = [...expected].sort()
  if (JSON.stringify(actualSorted) !== JSON.stringify(expectedSorted)) {
    throw new Error(`${label} must exactly match the contract: actual=${actualSorted.join(',')} expected=${expectedSorted.join(',')}`)
  }
}

function validateContract(contract, expectedStage) {
  requireObject(contract, 'evaluator contract')
  if (expectedStage === 'blind') {
    requireExactKeys(contract, ['evidenceIds'], 'blind evaluator contract')
    return { evidenceIds: requireUniqueIds(contract.evidenceIds, 'contract.evidenceIds', { minItems: 1 }) }
  }
  requireExactKeys(contract, ['criterionIds', 'evidenceIds', 'deterministicEvidenceIds', 'hardFailureRules'], 'target evaluator contract')
  const criterionIds = requireUniqueIds(contract.criterionIds, 'contract.criterionIds', { minItems: 1 })
  if (!Array.isArray(contract.hardFailureRules)) throw new Error('contract.hardFailureRules must be an array')
  const hardFailureRules = new Map()
  for (const [index, rule] of contract.hardFailureRules.entries()) {
    requireObject(rule, `contract.hardFailureRules[${index}]`)
    requireExactKeys(rule, HARD_FAILURE_RULE_KEYS, `contract.hardFailureRules[${index}]`)
    if (!criterionIds.has(rule.criterionId)) throw new Error(`contract.hardFailureRules[${index}].criterionId is unknown: ${rule.criterionId}`)
    if (hardFailureRules.has(rule.criterionId)) throw new Error(`contract.hardFailureRules contains duplicate criterionId: ${rule.criterionId}`)
    if (typeof rule.reason !== 'string' || !rule.reason) throw new Error(`contract.hardFailureRules[${index}].reason is invalid`)
    hardFailureRules.set(rule.criterionId, rule.reason)
  }
  return {
    criterionIds,
    evidenceIds: requireUniqueIds(contract.evidenceIds, 'contract.evidenceIds'),
    deterministicEvidenceIds: requireUniqueIds(contract.deterministicEvidenceIds, 'contract.deterministicEvidenceIds'),
    hardFailureRules,
  }
}

function requireReferences(values, allowed, label) {
  const ids = requireUniqueIds(values, label)
  const unknown = [...ids].filter((id) => !allowed.has(id))
  if (unknown.length) throw new Error(`${label} contains unknown id(s): ${unknown.join(', ')}`)
}

function validateBlind(value, contract) {
  requireExactKeys(value, BLIND_KEYS, 'blind result')
  if (!Array.isArray(value.observations)) throw new Error('blind observations must be an array')
  const ids = new Set()
  for (const [index, item] of value.observations.entries()) {
    requireObject(item, `observations[${index}]`)
    requireAllowedKeys(item, BLIND_OBSERVATION_KEYS, ['viewLabel'], `observations[${index}]`)
    if (typeof item.evidenceId !== 'string' || !item.evidenceId || ids.has(item.evidenceId)) throw new Error('blind evidenceId values must be non-empty and unique')
    ids.add(item.evidenceId)
    if ('viewLabel' in item && (typeof item.viewLabel !== 'string' || !item.viewLabel)) throw new Error(`observations[${index}].viewLabel is invalid`)
    for (const field of BLIND_OBSERVATION_KEYS.slice(1)) requireStringArray(item[field], `observations[${index}].${field}`)
  }
  requireExactIdSet(ids, contract.evidenceIds, 'blind observation evidenceIds')
  requireStringArray(value.crossImageConsistency, 'crossImageConsistency')
  requireStringArray(value.limitations, 'limitations')
}

function validateTarget(value, contract) {
  requireExactKeys(value, TARGET_KEYS, 'target result')
  if (!Array.isArray(value.criteria)) throw new Error('target criteria must be an array')
  const ids = new Set()
  for (const [index, item] of value.criteria.entries()) {
    requireObject(item, `criteria[${index}]`)
    requireExactKeys(item, TARGET_CRITERION_KEYS, `criteria[${index}]`)
    if (typeof item.criterionId !== 'string' || !item.criterionId || ids.has(item.criterionId)) throw new Error('target criterionId values must be non-empty and unique')
    ids.add(item.criterionId)
    if (!['pass', 'fail', 'unverified'].includes(item.status)) throw new Error(`criteria[${index}].status is invalid`)
    if (typeof item.confidence !== 'number' || item.confidence < 0 || item.confidence > 1) throw new Error(`criteria[${index}].confidence is invalid`)
    requireReferences(item.evidenceIds, contract.evidenceIds, `criteria[${index}].evidenceIds`)
    requireReferences(item.deterministicEvidenceIds, contract.deterministicEvidenceIds, `criteria[${index}].deterministicEvidenceIds`)
    if (typeof item.rationale !== 'string' || !item.rationale) throw new Error(`criteria[${index}].rationale is invalid`)
    requireStringArray(item.uncertainty, `criteria[${index}].uncertainty`)
  }
  requireExactIdSet(ids, contract.criterionIds, 'target criterionIds')
  requireObject(value.overall, 'overall')
  requireExactKeys(value.overall, TARGET_OVERALL_KEYS, 'overall')
  for (const field of ['coreGoalStatus', 'visualStatus']) {
    if (!['pass', 'fail', 'unverified'].includes(value.overall[field])) throw new Error(`overall.${field} is invalid`)
  }
  const criticalStatuses = value.criteria
    .filter((item) => contract.hardFailureRules.has(item.criterionId))
    .map((item) => item.status)
  const expectedCoreGoalStatus = criticalStatuses.includes('fail')
    ? 'fail'
    : criticalStatuses.includes('unverified') ? 'unverified' : 'pass'
  if (value.overall.coreGoalStatus !== expectedCoreGoalStatus) {
    throw new Error(`overall.coreGoalStatus must be ${expectedCoreGoalStatus} from critical criterion statuses`)
  }
  requireStringArray(value.overall.conflicts, 'overall.conflicts')
  requireStringArray(value.overall.limitations, 'overall.limitations')
  return value.criteria
    .filter((item) => item.status === 'fail' && contract.hardFailureRules.has(item.criterionId))
    .map((item) => ({ criterionId: item.criterionId, reason: contract.hardFailureRules.get(item.criterionId) }))
}

export function normalizeEvaluatorJson(text, expectedStage, contract) {
  if (!['blind', 'target'].includes(expectedStage)) throw new Error('expectedStage must be blind or target')
  const validatedContract = validateContract(contract, expectedStage)
  const raw = String(text).trim()
  let jsonText = raw
  let presentationNormalized = false
  const fenced = raw.match(/^```(?:json)?\s*\r?\n([\s\S]*?)\r?\n```$/i)
  if (fenced) {
    jsonText = fenced[1].trim()
    presentationNormalized = true
  } else if (raw.includes('```')) {
    throw new Error('evaluator response contains unsupported code fences or extra text')
  }
  let value
  try {
    value = JSON.parse(jsonText)
  } catch (error) {
    throw new Error(`evaluator response is not valid JSON: ${error instanceof Error ? error.message : String(error)}`)
  }
  requireObject(value, 'evaluator result')
  if (value.schemaVersion !== 1) throw new Error('evaluator result schemaVersion must be 1')
  if (value.stage !== expectedStage) throw new Error(`evaluator result stage must be ${expectedStage}`)
  if (expectedStage === 'blind') validateBlind(value, validatedContract)
  else value = { ...value, hardFailures: validateTarget(value, validatedContract) }
  return { value, presentationNormalized }
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
if (isMain) {
  const [command, ...values] = process.argv.slice(2)
  const option = (name) => {
    const index = values.indexOf(name)
    return index >= 0 ? values[index + 1] : undefined
  }
  if (command !== 'normalize' || !option('--input') || !option('--stage') || !option('--contract') || !option('--out')) {
    console.error('usage: node tools/benchmark-evaluator.mjs normalize --input <text-file> --stage blind|target --contract <ids.json> --out <json-file>')
    process.exitCode = 2
  } else {
    try {
      const result = normalizeEvaluatorJson(
        fs.readFileSync(path.resolve(option('--input')), 'utf8'),
        option('--stage'),
        JSON.parse(fs.readFileSync(path.resolve(option('--contract')), 'utf8')),
      )
      const out = path.resolve(option('--out'))
      fs.mkdirSync(path.dirname(out), { recursive: true })
      fs.writeFileSync(out, `${JSON.stringify(result.value, null, 2)}\n`, 'utf8')
      console.log(JSON.stringify({ out, presentationNormalized: result.presentationNormalized }, null, 2))
    } catch (error) {
      console.error(error instanceof Error ? error.message : String(error))
      process.exitCode = 1
    }
  }
}
