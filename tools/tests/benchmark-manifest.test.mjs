import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  agentSurfaceHash,
  canonicalJson,
  listAgentSurfaceFiles,
  publicBriefAgentPayload,
  resolveHipArtifactPath,
  sha256File,
  sha256Json,
  validateAllowedAnswers,
  validateEvaluationResult,
  validateProtocolManifest,
  validatePublicBrief,
  validateRunInputs,
  validateRunManifest,
  validateSeedFixture,
  validateSeedFixtureManifest,
  validateSmokeRun,
} from '../benchmark-manifest.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const hash = 'a'.repeat(64)
const hash2 = 'c'.repeat(64)
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
    targetPromptSha256: hash2,
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
assert.throws(() => validateProtocolManifest({
  ...protocol,
  evaluation: { ...protocol.evaluation, targetPromptSha256: hash },
}), /independently sealed/)
assert.throws(() => validateProtocolManifest({ ...protocol, unexpected: true }), /unsupported field/)
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
assert.throws(() => validateRunManifest({ ...run, unexpected: true }), /unsupported field/)
assert.throws(() => validateRunManifest({
  ...run,
  agentExposure: { ...run.agentExposure, evaluatorMaterialExposed: true },
}), /invalidate contaminated runs/)
assert.throws(() => validateRunManifest({
  ...run,
  startedAt: '2026-08-29T00:00:00.000Z',
  finishedAt: '2026-08-28T00:00:00.000Z',
}), /finishedAt must not be earlier/)
assert.throws(() => validateRunManifest({ ...run, status: 'failed' }), /terminal run requires finishedAt/)

const brief = {
  schemaVersion: 1,
  briefId: 'sealed-brief',
  capabilityFamily: 'mechanical',
  instanceRole: 'calibration',
  language: 'zh-CN',
  agentMessage: 'A normal user request lives in the sealed store.',
  resources: [{ resourceId: 'reference-1', sha256: hash2, mediaType: 'image/png' }],
  evaluatorMaterialExposed: false,
}
assert.equal(validatePublicBrief(brief), brief)
assert.throws(() => validatePublicBrief({ ...brief, evaluatorHint: 'hidden' }), /unsupported field/)
assert.deepEqual(publicBriefAgentPayload(brief), {
  message: brief.agentMessage,
  resources: brief.resources,
})
assert.equal('instanceRole' in publicBriefAgentPayload(brief), false)
assert.throws(() => validatePublicBrief({ ...brief, evaluatorMaterialExposed: true }), /must not expose evaluator material/)
assert.throws(() => validatePublicBrief({
  ...brief,
  resources: [...brief.resources, { ...brief.resources[0] }],
}), /resourceId values must be unique/)

const answers = {
  schemaVersion: 1,
  answerSetId: 'sealed-answers',
  publicBriefSha256: hash,
  entries: [{
    questionKey: 'output-format',
    questionPatternSha256: hash2,
    category: 'output-format',
    answer: 'Use the format stated by the user.',
    maxUses: 1,
    containsImplementationGuidance: false,
    containsEvaluatorMaterial: false,
  }],
}
assert.equal(validateAllowedAnswers(answers, { publicBriefSha256: hash }), answers)
assert.throws(() => validateAllowedAnswers(answers, { publicBriefSha256: hash2 }), /does not match/)
assert.throws(() => validateAllowedAnswers({
  ...answers,
  entries: [{ ...answers.entries[0], containsImplementationGuidance: true }],
}), /must not contain implementation guidance/)

const evaluation = {
  schemaVersion: 1,
  runId: run.runId,
  evaluatorSpecSha256: hash,
  inputs: {
    deterministicEvidenceSha256: hash,
    blindVisualInputSha256: hash,
    targetInputSha256: hash2,
  },
  hardFailures: [],
  scores: {
    coreDelivery: 32,
    objectiveEvidence: 20,
    independentVisual: 20,
    honestDelivery: 8,
  },
  total: 80,
  hardFailure: false,
  coreSuccess: true,
  claimLevel: 'local-regression',
  blindResultSha256: hash,
  targetResultSha256: hash2,
}
const completedRun = {
  ...run,
  status: 'completed',
  finishedAt: '2026-08-28T00:01:00.000Z',
  terminationReason: 'completed',
}
assert.equal(validateEvaluationResult(evaluation, { runManifest: completedRun }), evaluation)
const evaluatedRun = {
  ...completedRun,
  evaluation: {
    hardFailure: false,
    score: 80,
    claimLevel: 'local-regression',
    blindResultSha256: hash,
    targetResultSha256: hash2,
  },
}
assert.equal(validateEvaluationResult(evaluation, { runManifest: evaluatedRun }), evaluation)
assert.throws(() => validateEvaluationResult(evaluation, {
  runManifest: { ...evaluatedRun, evaluation: { ...evaluatedRun.evaluation, score: 81 } },
}), /total does not match/)
assert.throws(() => validateEvaluationResult({ ...evaluation, total: 79 }, { runManifest: completedRun }), /total must equal/)
assert.throws(() => validateEvaluationResult({
  ...evaluation,
  inputs: { ...evaluation.inputs, targetInputSha256: hash },
}), /independently sealed/)
assert.throws(() => validateEvaluationResult({
  ...evaluation,
  hardFailures: ['core-output-missing'],
}), /hardFailure must match/)

const smokeRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-smoke-fixture-'))
const repositoryRoot = path.join(smokeRoot, 'repo')
const hipRoot = path.join(smokeRoot, 'hip')
const traceRoot = path.join(smokeRoot, 'trace')
fs.mkdirSync(repositoryRoot, { recursive: true })
fs.mkdirSync(path.join(hipRoot, 'render'), { recursive: true })
fs.mkdirSync(path.join(hipRoot, 'cache'), { recursive: true })
fs.mkdirSync(traceRoot, { recursive: true })
fs.writeFileSync(path.join(hipRoot, 'smoke.hip'), 'hip')
fs.writeFileSync(path.join(hipRoot, 'render', 'review.png'), 'png')
fs.writeFileSync(path.join(hipRoot, 'cache', 'frame.bgeo.sc'), 'cache')
const traceFile = path.join(traceRoot, 'session.jsonl.zstd')
fs.writeFileSync(traceFile, 'trace')

const seed = {
  schemaVersion: 1,
  fixtureId: 'seed-test',
  capabilityFamily: 'mechanical',
  instanceRole: 'calibration',
  generator: {
    id: 'empty-scene-generator',
    version: '1',
    scriptSha256: hash,
    parametersSha256: hash2,
    deterministic: true,
  },
  output: {
    hip: '$HIP/smoke.hip',
    sha256: sha256File(path.join(hipRoot, 'smoke.hip')),
    identitySha256: hash2,
    houdini: '21.0.440',
  },
  evaluatorMaterialExposed: false,
}
assert.equal(validateSeedFixtureManifest(seed), seed)
assert.equal(validateSeedFixture(seed, { hipRoot }).fixtureId, 'seed-test')
assert.throws(() => validateSeedFixture({
  ...seed,
  output: { ...seed.output, sha256: hash },
}, { hipRoot }), /sha256 does not match/)
assert.throws(() => validateSeedFixtureManifest({
  ...seed,
  generator: { ...seed.generator, deterministic: false },
}), /deterministic must be true/)

const sealedRoot = path.join(smokeRoot, 'sealed')
fs.mkdirSync(sealedRoot, { recursive: true })
const briefFile = path.join(sealedRoot, 'brief.json')
fs.writeFileSync(briefFile, JSON.stringify(brief))
const linkedAnswers = { ...answers, publicBriefSha256: sha256File(briefFile) }
const answersFile = path.join(sealedRoot, 'answers.json')
fs.writeFileSync(answersFile, JSON.stringify(linkedAnswers))
const inputRun = {
  ...run,
  agentExposure: {
    ...run.agentExposure,
    publicBriefSha256: sha256File(briefFile),
    allowedAnswersSha256: sha256File(answersFile),
    seedSceneSha256: seed.output.sha256,
    resourceSha256: brief.resources.map((resource) => resource.sha256),
  },
}
const inputSummary = validateRunInputs({
  runManifest: inputRun,
  publicBrief: brief,
  publicBriefSha256: sha256File(briefFile),
  allowedAnswers: linkedAnswers,
  allowedAnswersSha256: sha256File(answersFile),
  seedFixture: seed,
  hipRoot,
})
assert.equal(inputSummary.seedSceneSha256, seed.output.sha256)
assert.throws(() => validateRunInputs({
  runManifest: { ...inputRun, agentExposure: { ...inputRun.agentExposure, resourceSha256: [] } },
  publicBrief: brief,
  publicBriefSha256: sha256File(briefFile),
  allowedAnswers: linkedAnswers,
  allowedAnswersSha256: sha256File(answersFile),
  seedFixture: seed,
  hipRoot,
}), /resourceSha256 does not exactly match/)

const smoke = {
  ...run,
  runId: 'smoke-test',
  phase: 'smoke',
  status: 'completed',
  finishedAt: '2026-08-28T00:01:00.000Z',
  terminationReason: 'smoke completed',
  evidence: {
    trace: traceFile,
    hip: '$HIP/smoke.hip',
    cache: ['$HIP/cache/frame.bgeo.sc'],
    render: ['$HIP/render/review.png'],
    finalNodes: ['/obj/SMOKE_OUT'],
  },
}
const smokeSummary = validateSmokeRun(smoke, { hipRoot, repositoryRoot })
assert.equal(smokeSummary.runId, 'smoke-test')
assert.equal(smokeSummary.hip.bytes, 3)
assert.equal(smokeSummary.render.length, 1)
assert.equal(resolveHipArtifactPath('$HIP/render/review.png', hipRoot), fs.realpathSync.native(path.join(hipRoot, 'render', 'review.png')))
assert.throws(() => resolveHipArtifactPath('$HIP/../escape.hip', hipRoot), /escapes \$HIP/)
assert.throws(() => validateSmokeRun({
  ...smoke,
  evidence: { ...smoke.evidence, render: [] },
}, { hipRoot, repositoryRoot }), /evidence.render must be an array with at least 1/)
const repositoryTrace = path.join(repositoryRoot, 'trace.jsonl.zstd')
fs.writeFileSync(repositoryTrace, 'trace')
assert.throws(() => validateSmokeRun({
  ...smoke,
  evidence: { ...smoke.evidence, trace: repositoryTrace },
}, { hipRoot, repositoryRoot }), /trace must stay outside/)
fs.rmSync(smokeRoot, { recursive: true })

for (const schema of [
  'protocol-manifest.schema.json',
  'run-manifest.schema.json',
  'public-brief.schema.json',
  'allowed-answers.schema.json',
  'seed-fixture.schema.json',
  'seed-generator-input.schema.json',
  'model-capability-smoke.schema.json',
  'evaluator-prompt.schema.json',
  'evaluator-prompt-baseline.schema.json',
  'evaluation-result.schema.json',
]) {
  const parsed = JSON.parse(fs.readFileSync(path.join(root, 'benchmark', schema), 'utf8'))
  assert.equal(parsed.$schema, 'https://json-schema.org/draft/2020-12/schema')
  assert.equal(parsed.additionalProperties, false)
  if (schema === 'run-manifest.schema.json') assert.ok(Array.isArray(parsed.allOf))
}

const modelCapability = JSON.parse(fs.readFileSync(path.join(root, 'benchmark', 'model-capability-baseline.json'), 'utf8'))
assert.equal(modelCapability.schemaVersion, 1)
assert.equal(modelCapability.input.toolsAvailable, false)
assert.deepEqual(
  modelCapability.models.map((item) => `${item.provider}/${item.model}`),
  ['kimi-coding/k3', 'apikeyfun/glm-5.3-flash'],
)
assert.ok(modelCapability.models.every((item) => item.transportOk && item.semanticOk))
assert.equal(modelCapability.models[0].adapterImageDeclared, true)
assert.equal(modelCapability.models[1].adapterImageDeclared, null)
assert.equal(modelCapability.models[1].minimumVerifiedMaxTokens, 1500)

const evaluatorBaseline = JSON.parse(fs.readFileSync(path.join(root, 'benchmark', 'evaluator-prompt-baseline.json'), 'utf8'))
const blindPrompt = JSON.parse(fs.readFileSync(path.join(root, 'benchmark', 'evaluator-prompts', 'blind-visual-v1.json'), 'utf8'))
const targetPrompt = JSON.parse(fs.readFileSync(path.join(root, 'benchmark', 'evaluator-prompts', 'target-verification-v1.json'), 'utf8'))
assert.equal(evaluatorBaseline.evaluator.model, 'qwen-vl-max')
assert.equal(evaluatorBaseline.prompts.blind.canonicalSha256, sha256Json(blindPrompt))
assert.equal(evaluatorBaseline.prompts.target.canonicalSha256, sha256Json(targetPrompt))
assert.notEqual(evaluatorBaseline.prompts.blind.canonicalSha256, evaluatorBaseline.prompts.target.canonicalSha256)
assert.equal(evaluatorBaseline.status, 'verified')
assert.notEqual(evaluatorBaseline.smoke.blindInputSha256, evaluatorBaseline.smoke.targetInputSha256)
assert.equal(evaluatorBaseline.smoke.blindSemanticOk, true)
assert.equal(evaluatorBaseline.smoke.targetSemanticOk, true)
assert.equal(evaluatorBaseline.smoke.blindTransportFailures, 1)
assert.equal(blindPrompt.stage, 'blind')
assert.equal(targetPrompt.stage, 'target')
assert.equal(blindPrompt.executionAgentExposed, false)
assert.equal(targetPrompt.executionAgentExposed, false)

const packageJson = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'))
assert.ok(!packageJson.files.includes('benchmark'), 'sealed benchmark administration must not ship in the production npm package')

console.log('benchmark manifest and surface-hash tests passed')
