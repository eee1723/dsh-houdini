import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const BLIND_KEYS = ['schemaVersion', 'stage', 'observations', 'crossImageConsistency', 'limitations']
const BLIND_OBSERVATION_KEYS = ['evidenceId', 'visibleSubjects', 'geometry', 'materialColor', 'lighting', 'composition', 'defects', 'uncertainty']
const TARGET_KEYS = ['schemaVersion', 'stage', 'criteria', 'hardFailures', 'overall']
const TARGET_CRITERION_KEYS = ['criterionId', 'status', 'confidence', 'evidenceIds', 'deterministicEvidenceIds', 'rationale', 'uncertainty']
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

function validateBlind(value) {
  requireExactKeys(value, BLIND_KEYS, 'blind result')
  if (!Array.isArray(value.observations)) throw new Error('blind observations must be an array')
  for (const [index, item] of value.observations.entries()) {
    requireObject(item, `observations[${index}]`)
    requireAllowedKeys(item, BLIND_OBSERVATION_KEYS, ['viewLabel'], `observations[${index}]`)
    if (typeof item.evidenceId !== 'string' || !item.evidenceId) throw new Error(`observations[${index}].evidenceId is invalid`)
    if ('viewLabel' in item && (typeof item.viewLabel !== 'string' || !item.viewLabel)) throw new Error(`observations[${index}].viewLabel is invalid`)
    for (const field of BLIND_OBSERVATION_KEYS.slice(1)) requireStringArray(item[field], `observations[${index}].${field}`)
  }
  requireStringArray(value.crossImageConsistency, 'crossImageConsistency')
  requireStringArray(value.limitations, 'limitations')
}

function validateTarget(value) {
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
    requireStringArray(item.evidenceIds, `criteria[${index}].evidenceIds`)
    requireStringArray(item.deterministicEvidenceIds, `criteria[${index}].deterministicEvidenceIds`)
    if (typeof item.rationale !== 'string' || !item.rationale) throw new Error(`criteria[${index}].rationale is invalid`)
    requireStringArray(item.uncertainty, `criteria[${index}].uncertainty`)
  }
  if (!Array.isArray(value.hardFailures)) throw new Error('hardFailures must be an array')
  requireObject(value.overall, 'overall')
  requireExactKeys(value.overall, TARGET_OVERALL_KEYS, 'overall')
  for (const field of ['coreGoalStatus', 'visualStatus']) {
    if (!['pass', 'fail', 'unverified'].includes(value.overall[field])) throw new Error(`overall.${field} is invalid`)
  }
  requireStringArray(value.overall.conflicts, 'overall.conflicts')
  requireStringArray(value.overall.limitations, 'overall.limitations')
}

export function normalizeEvaluatorJson(text, expectedStage) {
  if (!['blind', 'target'].includes(expectedStage)) throw new Error('expectedStage must be blind or target')
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
  if (expectedStage === 'blind') validateBlind(value)
  else validateTarget(value)
  return { value, presentationNormalized }
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
if (isMain) {
  const [command, ...values] = process.argv.slice(2)
  const option = (name) => {
    const index = values.indexOf(name)
    return index >= 0 ? values[index + 1] : undefined
  }
  if (command !== 'normalize' || !option('--input') || !option('--stage') || !option('--out')) {
    console.error('usage: node tools/benchmark-evaluator.mjs normalize --input <text-file> --stage blind|target --out <json-file>')
    process.exitCode = 2
  } else {
    try {
      const result = normalizeEvaluatorJson(fs.readFileSync(path.resolve(option('--input')), 'utf8'), option('--stage'))
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
