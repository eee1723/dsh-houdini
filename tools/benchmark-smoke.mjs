import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  resolveHipArtifactPath,
  sha256File,
  sha256Json,
  validateProtocolManifest,
  validatePublicBrief,
  validateSealedInstanceManifest,
  validateSeedFixture,
} from './benchmark-manifest.mjs'

const FAMILIES = ['mechanical', 'simulation', 'lookdev']
const PHASES = ['smoke', 'discovery']

function loadJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'))
}

function requireFile(file, label) {
  if (!fs.existsSync(file) || !fs.statSync(file).isFile() || fs.statSync(file).size <= 0) {
    throw new Error(`${label} is missing or empty: ${file}`)
  }
  return file
}

export function prepareIsolatedRunWorkspace({ kitRoot, family, runId, protocolFile, phase, model }) {
  if (!FAMILIES.includes(family)) throw new Error(`unsupported family: ${family}`)
  if (!PHASES.includes(phase)) throw new Error(`unsupported isolated run phase: ${phase}`)
  if (typeof runId !== 'string' || !/^[a-z0-9][a-z0-9._-]*$/.test(runId)) throw new Error('runId is invalid')
  const kit = path.resolve(kitRoot)
  const protocolPath = path.resolve(protocolFile)
  const protocol = loadJson(requireFile(protocolPath, 'protocol manifest'))
  validateProtocolManifest(protocol)
  if (!protocol.execution.models.includes(model)) throw new Error(`model is not frozen in the protocol: ${model}`)

  const operatorRoot = path.join(kit, 'operator', family)
  const sourceHipRoot = path.join(kit, 'hip', family)
  const briefFile = requireFile(path.join(operatorRoot, 'public-brief.json'), 'public brief')
  const answersFile = requireFile(path.join(operatorRoot, 'allowed-answers.json'), 'allowed answers')
  const seedFile = requireFile(path.join(operatorRoot, 'seed-fixture.json'), 'seed fixture')
  const evaluatorFile = requireFile(path.join(operatorRoot, 'evaluator-spec.json'), 'evaluator spec')
  const sealedFile = requireFile(path.join(operatorRoot, 'sealed-manifest.json'), 'sealed manifest')
  const messageFile = requireFile(path.join(operatorRoot, 'agent-message.txt'), 'agent message')

  const brief = loadJson(briefFile)
  validatePublicBrief(brief)
  if (brief.capabilityFamily !== family || brief.instanceRole !== 'calibration') {
    throw new Error('public brief must match the requested calibration family')
  }
  if (fs.readFileSync(messageFile, 'utf8') !== brief.agentMessage) {
    throw new Error('agent-message.txt does not exactly match publicBrief.agentMessage')
  }
  const seed = loadJson(seedFile)
  validateSeedFixture(seed, { hipRoot: sourceHipRoot })
  const sealed = loadJson(sealedFile)
  validateSealedInstanceManifest(sealed)
  if (sealed.capabilityFamily !== family || sealed.instanceRole !== 'calibration') {
    throw new Error('sealed manifest must match the requested calibration family')
  }
  if (sha256Json(sealed) !== protocol.sealedInstances[family].calibration) {
    throw new Error('sealed calibration hash does not match the frozen protocol')
  }
  const expectedFiles = {
    publicBriefSha256: sha256File(briefFile),
    allowedAnswersSha256: sha256File(answersFile),
    seedFixtureSha256: sha256File(seedFile),
    evaluatorSpecSha256: sha256File(evaluatorFile),
  }
  for (const [field, actual] of Object.entries(expectedFiles)) {
    if (sealed.files[field] !== actual) throw new Error(`${field} does not match the sealed manifest`)
  }

  const sourceSeedHip = resolveHipArtifactPath(seed.output.hip, sourceHipRoot)
  const executionWorkspace = path.join(kit, 'execution', family, runId)
  if (fs.existsSync(executionWorkspace)) throw new Error(`execution workspace already exists: ${executionWorkspace}`)
  fs.mkdirSync(executionWorkspace, { recursive: true })
  const workHip = path.join(executionWorkspace, 'work.hip')
  const publicMessage = path.join(executionWorkspace, 'agent-message.txt')
  fs.copyFileSync(sourceSeedHip, workHip, fs.constants.COPYFILE_EXCL)
  fs.copyFileSync(messageFile, publicMessage, fs.constants.COPYFILE_EXCL)
  if (sha256File(workHip) !== seed.output.sha256) throw new Error('work.hip bytes do not match the sealed seed scene')
  const visibleFiles = fs.readdirSync(executionWorkspace).sort()
  if (JSON.stringify(visibleFiles) !== JSON.stringify(['agent-message.txt', 'work.hip'])) {
    throw new Error(`execution workspace contains unexpected files: ${visibleFiles.join(', ')}`)
  }

  const preflight = {
    schemaVersion: 1,
    preparedAt: new Date().toISOString(),
    protocolVersion: protocol.protocolVersion,
    protocolManifestSha256: sha256File(protocolPath),
    family,
    phase,
    instanceRole: 'calibration',
    model,
    instanceSealedSha256: protocol.sealedInstances[family].calibration,
    evaluatorSpecSha256: sealed.files.evaluatorSpecSha256,
    publicBriefSha256: sealed.files.publicBriefSha256,
    allowedAnswersSha256: sealed.files.allowedAnswersSha256,
    seedSceneSha256: seed.output.sha256,
    executionWorkspace,
    workHip,
    agentVisibleFiles: visibleFiles,
    evaluatorMaterialExposed: false,
  }
  const preflightFile = path.join(operatorRoot, `${runId}-preflight.json`)
  fs.writeFileSync(preflightFile, `${JSON.stringify(preflight, null, 2)}\n`, { encoding: 'utf8', flag: 'wx' })
  return { ...preflight, preflightFile }
}

export function prepareSmokeWorkspace({ kitRoot, family, runId, protocolFile }) {
  const protocol = loadJson(requireFile(path.resolve(protocolFile), 'protocol manifest'))
  validateProtocolManifest(protocol)
  return prepareIsolatedRunWorkspace({
    kitRoot,
    family,
    runId,
    protocolFile,
    phase: 'smoke',
    model: protocol.execution.models[0],
  })
}

function option(values, name) {
  const index = values.indexOf(name)
  return index >= 0 ? values[index + 1] : undefined
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
if (isMain) {
  const [command, ...values] = process.argv.slice(2)
  if (command !== 'prepare' || !option(values, '--kit') || !option(values, '--family') || !option(values, '--run-id') || !option(values, '--protocol')) {
    console.error('usage: node tools/benchmark-smoke.mjs prepare --kit <root> --family <family> --run-id <id> --protocol <protocol.json>')
    process.exitCode = 2
  } else {
    try {
      console.log(JSON.stringify(prepareSmokeWorkspace({
        kitRoot: option(values, '--kit'),
        family: option(values, '--family'),
        runId: option(values, '--run-id'),
        protocolFile: option(values, '--protocol'),
      }), null, 2))
    } catch (error) {
      console.error(error instanceof Error ? error.message : String(error))
      process.exitCode = 1
    }
  }
}
