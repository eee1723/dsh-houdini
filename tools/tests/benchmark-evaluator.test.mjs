import assert from 'node:assert/strict'

import { normalizeEvaluatorJson } from '../benchmark-evaluator.mjs'

const blind = { schemaVersion: 1, stage: 'blind', observations: [{ evidenceId: 'a', visibleSubjects: [], geometry: [], materialColor: [], lighting: [], composition: [], defects: [], uncertainty: [] }], crossImageConsistency: [], limitations: [] }
const target = { schemaVersion: 1, stage: 'target', criteria: [{ criterionId: 'c', status: 'unverified', confidence: 0.5, evidenceIds: [], deterministicEvidenceIds: [], rationale: 'insufficient evidence', uncertainty: ['missing view'] }], hardFailures: [], overall: { coreGoalStatus: 'unverified', visualStatus: 'unverified', conflicts: [], limitations: [] } }

assert.equal(normalizeEvaluatorJson(JSON.stringify(blind), 'blind').presentationNormalized, false)
assert.equal(normalizeEvaluatorJson(JSON.stringify({ ...blind, observations: [{ ...blind.observations[0], viewLabel: 'anonymous-closeup' }] }), 'blind').value.observations[0].viewLabel, 'anonymous-closeup')
assert.equal(normalizeEvaluatorJson(`\`\`\`json\n${JSON.stringify(blind)}\n\`\`\``, 'blind').presentationNormalized, true)
assert.deepEqual(normalizeEvaluatorJson(`\`\`\`\n${JSON.stringify(target)}\n\`\`\``, 'target').value, target)
assert.throws(() => normalizeEvaluatorJson(`result:\n\`\`\`json\n${JSON.stringify(blind)}\n\`\`\``, 'blind'), /unsupported code fences/)
assert.throws(() => normalizeEvaluatorJson(JSON.stringify({ ...blind, stage: 'target' }), 'blind'), /stage must be blind/)
assert.throws(() => normalizeEvaluatorJson(JSON.stringify({ ...target, criteria: [{ ...target.criteria[0], status: 'maybe' }] }), 'target'), /status is invalid/)
assert.throws(() => normalizeEvaluatorJson('{}', 'blind'), /schemaVersion/)
assert.throws(() => normalizeEvaluatorJson(JSON.stringify({ ...blind, observations: [{ ...blind.observations[0], leakedGoal: 'x' }] }), 'blind'), /unsupported=leakedGoal/)

console.log('evaluator JSON normalization tests passed')
