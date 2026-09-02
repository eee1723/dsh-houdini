import assert from 'node:assert/strict'

import { normalizeEvaluatorJson } from '../benchmark-evaluator.mjs'

const blind = { schemaVersion: 1, stage: 'blind', observations: [{ evidenceId: 'a', visibleSubjects: [], geometry: [], materialColor: [], lighting: [], composition: [], defects: [], uncertainty: [] }], crossImageConsistency: [], limitations: [] }
const target = { schemaVersion: 1, stage: 'target', criteria: [{ criterionId: 'c', status: 'unverified', confidence: 0.5, evidenceIds: ['a'], deterministicEvidenceIds: ['d'], rationale: 'insufficient evidence', uncertainty: ['missing view'] }], overall: { coreGoalStatus: 'unverified', visualStatus: 'unverified', conflicts: [], limitations: [] } }
const blindContract = { evidenceIds: ['a'] }
const targetContract = { criterionIds: ['c'], evidenceIds: ['a'], deterministicEvidenceIds: ['d'], hardFailureRules: [{ criterionId: 'c', reason: 'critical criterion failed' }] }
const normalizedTarget = { ...target, hardFailures: [] }

assert.equal(normalizeEvaluatorJson(JSON.stringify(blind), 'blind', blindContract).presentationNormalized, false)
assert.equal(normalizeEvaluatorJson(JSON.stringify({ ...blind, observations: [{ ...blind.observations[0], viewLabel: 'anonymous-closeup' }] }), 'blind', blindContract).value.observations[0].viewLabel, 'anonymous-closeup')
assert.equal(normalizeEvaluatorJson(`\`\`\`json\n${JSON.stringify(blind)}\n\`\`\``, 'blind', blindContract).presentationNormalized, true)
assert.deepEqual(normalizeEvaluatorJson(`\`\`\`\n${JSON.stringify(target)}\n\`\`\``, 'target', targetContract).value, normalizedTarget)
assert.throws(() => normalizeEvaluatorJson(`result:\n\`\`\`json\n${JSON.stringify(blind)}\n\`\`\``, 'blind', blindContract), /unsupported code fences/)
assert.throws(() => normalizeEvaluatorJson(JSON.stringify({ ...blind, stage: 'target' }), 'blind', blindContract), /stage must be blind/)
assert.throws(() => normalizeEvaluatorJson(JSON.stringify({ ...target, criteria: [{ ...target.criteria[0], status: 'maybe' }] }), 'target', targetContract), /status is invalid/)
assert.throws(() => normalizeEvaluatorJson('{}', 'blind', blindContract), /schemaVersion/)
assert.throws(() => normalizeEvaluatorJson(JSON.stringify({ ...blind, observations: [{ ...blind.observations[0], leakedGoal: 'x' }] }), 'blind', blindContract), /unsupported=leakedGoal/)
assert.throws(() => normalizeEvaluatorJson(JSON.stringify(blind), 'blind', { evidenceIds: ['a', 'b'] }), /exactly match the contract/)
assert.throws(() => normalizeEvaluatorJson(JSON.stringify({ ...blind, observations: [...blind.observations, blind.observations[0]] }), 'blind', blindContract), /non-empty and unique/)
assert.throws(() => normalizeEvaluatorJson(JSON.stringify({ ...target, criteria: [{ ...target.criteria[0], criterionId: 'unexpected' }] }), 'target', targetContract), /exactly match the contract/)
assert.throws(() => normalizeEvaluatorJson(JSON.stringify({ ...target, criteria: [{ ...target.criteria[0], evidenceIds: ['d'] }] }), 'target', targetContract), /unknown id\(s\): d/)
assert.throws(() => normalizeEvaluatorJson(JSON.stringify({ ...target, criteria: [{ ...target.criteria[0], deterministicEvidenceIds: ['a'] }] }), 'target', targetContract), /unknown id\(s\): a/)
assert.throws(() => normalizeEvaluatorJson(JSON.stringify({ ...target, hardFailures: [] }), 'target', targetContract), /target result fields are invalid/)
const failedTarget = { ...target, criteria: [{ ...target.criteria[0], status: 'fail' }] }
const coherentFailedTarget = { ...failedTarget, overall: { ...failedTarget.overall, coreGoalStatus: 'fail' } }
assert.deepEqual(normalizeEvaluatorJson(JSON.stringify(coherentFailedTarget), 'target', targetContract).value, { ...coherentFailedTarget, hardFailures: [{ criterionId: 'c', reason: 'critical criterion failed' }] })
assert.throws(() => normalizeEvaluatorJson(JSON.stringify(failedTarget), 'target', targetContract), /coreGoalStatus must be fail/)
const passingTarget = { ...target, criteria: [{ ...target.criteria[0], status: 'pass' }], overall: { ...target.overall, coreGoalStatus: 'pass' } }
assert.deepEqual(normalizeEvaluatorJson(JSON.stringify(passingTarget), 'target', targetContract).value, { ...passingTarget, hardFailures: [] })
assert.throws(() => normalizeEvaluatorJson(JSON.stringify(target), 'target', { ...targetContract, hardFailureRules: [{ criterionId: 'missing', reason: 'x' }] }), /criterionId is unknown/)
assert.throws(() => normalizeEvaluatorJson(JSON.stringify(target), 'target'), /evaluator contract must be an object/)

console.log('evaluator JSON normalization tests passed')
