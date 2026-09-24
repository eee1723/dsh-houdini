import fs from 'node:fs'
import path from 'node:path'
import { suiteRoot, validateSuite } from './suite.mjs'

const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value)

// The V1 result schema uses only these JSON Schema keywords. Reject new keywords
// until this reader supports them, so schema changes cannot silently weaken the gate.
const supportedKeywords = new Set([
  '$schema', '$id', 'title', 'type', 'additionalProperties', 'required', 'properties',
  'const', 'enum', 'minLength', 'minimum', 'minItems', 'items', 'uniqueItems', 'format',
])

function matchesType(value, type) {
  if (type === 'null') return value === null
  if (type === 'array') return Array.isArray(value)
  if (type === 'object') return isObject(value)
  if (type === 'integer') return Number.isInteger(value)
  return typeof value === type
}

function checkSchema(value, schema, location) {
  for (const key of Object.keys(schema)) if (!supportedKeywords.has(key)) throw new Error(`unsupported review schema keyword: ${key}`)
  if (schema.type && ![schema.type].flat().some(type => matchesType(value, type))) throw new Error(`${location} has the wrong type`)
  if ('const' in schema && value !== schema.const) throw new Error(`${location} has the wrong fixed value`)
  if (schema.enum && !schema.enum.includes(value)) throw new Error(`${location} has an invalid value`)
  if (schema.minLength !== undefined && value.length < schema.minLength) throw new Error(`${location} is empty or too short`)
  if (schema.minimum !== undefined && value < schema.minimum) throw new Error(`${location} is below its minimum`)
  if (schema.format === 'date-time' && (!/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(value) || Number.isNaN(Date.parse(value)))) throw new Error(`${location} is not a date-time`)
  if (isObject(value)) {
    for (const key of schema.required ?? []) if (!(key in value)) throw new Error(`${location}.${key} is required`)
    if (schema.additionalProperties === false) for (const key of Object.keys(value)) if (!(key in (schema.properties ?? {}))) throw new Error(`${location}.${key} is not allowed`)
    for (const [key, child] of Object.entries(schema.properties ?? {})) if (key in value) checkSchema(value[key], child, `${location}.${key}`)
  }
  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) throw new Error(`${location} has too few items`)
    if (schema.uniqueItems && new Set(value.map(item => JSON.stringify(item))).size !== value.length) throw new Error(`${location} has duplicate items`)
    if (schema.items) value.forEach((item, index) => checkSchema(item, schema.items, `${location}[${index}]`))
  }
}

export function validateReviewResult(review, root = suiteRoot) {
  const { root: sourceRoot, manifest } = validateSuite(root)
  const schema = JSON.parse(fs.readFileSync(path.join(sourceRoot, manifest.reviewResultSchema), 'utf8'))
  checkSchema(review, schema, 'review')

  const item = manifest.cases.find(entry => entry.id === review.caseId)
  if (!item) throw new Error('review caseId is not in the suite')
  const checklist = JSON.parse(fs.readFileSync(path.join(sourceRoot, item.evaluator), 'utf8'))
  const expectedCriteria = new Set(checklist.criteria.map(criterion => criterion.id))
  const actualCriteria = new Set(review.criteria.map(criterion => criterion.id))
  if (actualCriteria.size !== review.criteria.length) throw new Error('review has duplicate criterion IDs')
  if (actualCriteria.size !== expectedCriteria.size || [...actualCriteria].some(id => !expectedCriteria.has(id))) throw new Error('review criterion IDs do not match the evaluator checklist')

  const evidenceIds = new Set(review.evidence.map(evidence => evidence.id))
  if (evidenceIds.size !== review.evidence.length) throw new Error('review has duplicate evidence IDs')
  const evidenceById = new Map(review.evidence.map(evidence => [evidence.id, evidence]))
  if (!review.evidence.some(evidence => evidence.origin === 'reviewerProduced')) throw new Error('review needs independently produced evidence')
  for (const criterion of review.criteria) {
    if (criterion.evidenceIds.some(id => !evidenceIds.has(id))) throw new Error('criterion references an unknown evidence ID')
    const method = checklist.criteria.find(item => item.id === criterion.id).method
    if (criterion.status === 'pass' && method !== 'report' && !criterion.evidenceIds.some(id => evidenceById.get(id).origin === 'reviewerProduced')) {
      throw new Error(`passed criterion needs independent evidence: ${criterion.id}`)
    }
  }
  return { caseId: item.id, criteria: review.criteria.length, evidence: review.evidence.length }
}
