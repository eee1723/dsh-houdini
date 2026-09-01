import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  sha256File,
  sha256Json,
  validateAllowedAnswers,
  validateEvaluatorSpec,
  validatePublicBrief,
  validateSealedInstanceManifest,
  validateSeedFixtureManifest,
} from './benchmark-manifest.mjs'

function loadJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'))
}

function requireSameFamilyRole(entries) {
  const families = new Set(entries.map(([label, value]) => `${label}:${value.capabilityFamily}`))
  const familyValues = new Set(entries.map(([, value]) => value.capabilityFamily))
  if (familyValues.size !== 1) throw new Error(`capabilityFamily mismatch: ${[...families].join(', ')}`)
  const roles = new Set(entries.map(([label, value]) => `${label}:${value.instanceRole}`))
  const roleValues = new Set(entries.map(([, value]) => value.instanceRole))
  if (roleValues.size !== 1) throw new Error(`instanceRole mismatch: ${[...roles].join(', ')}`)
  return { capabilityFamily: entries[0][1].capabilityFamily, instanceRole: entries[0][1].instanceRole }
}

function parseResourceOptions(values) {
  const resources = new Map()
  for (const value of values) {
    const separator = value.indexOf('=')
    if (separator <= 0 || separator === value.length - 1) throw new Error('--resource must use resourceId=path')
    const resourceId = value.slice(0, separator)
    const file = path.resolve(value.slice(separator + 1))
    if (resources.has(resourceId)) throw new Error(`duplicate resource mapping: ${resourceId}`)
    if (!fs.existsSync(file) || !fs.statSync(file).isFile() || fs.statSync(file).size <= 0) {
      throw new Error(`resource file is missing or empty: ${file}`)
    }
    resources.set(resourceId, file)
  }
  return resources
}

function verifyResources(publicBrief, resourceFiles) {
  const expectedIds = new Set(publicBrief.resources.map((resource) => resource.resourceId))
  if (expectedIds.size !== resourceFiles.size || [...expectedIds].some((id) => !resourceFiles.has(id))) {
    throw new Error('resource mappings must exactly match public brief resourceId values')
  }
  const hashes = []
  for (const resource of publicBrief.resources) {
    const actual = sha256File(resourceFiles.get(resource.resourceId))
    if (actual !== resource.sha256) throw new Error(`resource sha256 mismatch: ${resource.resourceId}`)
    hashes.push(actual)
  }
  return hashes.sort()
}

export function sealInstance({
  publicBriefFile,
  allowedAnswersFile,
  seedFixtureFile,
  evaluatorSpecFile,
  resourceFiles = new Map(),
  productionSurfaceCommit,
  instanceId,
}) {
  const publicBrief = loadJson(publicBriefFile)
  const allowedAnswers = loadJson(allowedAnswersFile)
  const seedFixture = loadJson(seedFixtureFile)
  const evaluatorSpec = loadJson(evaluatorSpecFile)
  validatePublicBrief(publicBrief)
  const publicBriefSha256 = sha256File(publicBriefFile)
  validateAllowedAnswers(allowedAnswers, { publicBriefSha256 })
  validateSeedFixtureManifest(seedFixture)
  validateEvaluatorSpec(evaluatorSpec, { publicBriefSha256 })
  const common = requireSameFamilyRole([
    ['brief', publicBrief],
    ['seed', seedFixture],
    ['evaluator', evaluatorSpec],
  ])
  const resourceSha256 = verifyResources(publicBrief, resourceFiles)
  const manifest = {
    schemaVersion: 1,
    instanceId: instanceId || publicBrief.briefId,
    capabilityFamily: common.capabilityFamily,
    instanceRole: common.instanceRole,
    files: {
      publicBriefSha256,
      allowedAnswersSha256: sha256File(allowedAnswersFile),
      seedFixtureSha256: sha256File(seedFixtureFile),
      evaluatorSpecSha256: sha256File(evaluatorSpecFile),
      resourceSha256,
    },
    releasePolicy: {
      productionSurfaceCommit,
      revealAfterSurfaceFreeze: true,
      becomesCalibrationAfterReveal: true,
    },
    evaluatorMaterialExposed: false,
  }
  validateSealedInstanceManifest(manifest)
  return { manifest, sealedInstanceSha256: sha256Json(manifest) }
}

function optionsOf(values) {
  const map = new Map()
  for (let index = 0; index < values.length; index += 1) {
    const key = values[index]
    if (!key.startsWith('--')) continue
    if (key === '--resource') {
      const current = map.get(key) || []
      current.push(values[++index])
      map.set(key, current)
    } else {
      map.set(key, values[++index])
    }
  }
  return map
}

function usage() {
  return [
    'usage: node tools/benchmark-instance.mjs seal',
    '  --brief <public-brief.json> --answers <allowed-answers.json>',
    '  --seed <seed-fixture.json> --evaluator <evaluator-spec.json>',
    '  --commit <production-git-sha> --out <sealed-manifest.json>',
    '  [--instance-id <id>] [--resource <resourceId=path>]...',
  ].join('\n')
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
if (isMain) {
  const [command, ...values] = process.argv.slice(2)
  const options = optionsOf(values)
  const required = ['--brief', '--answers', '--seed', '--evaluator', '--commit', '--out']
  if (command !== 'seal' || required.some((key) => !options.get(key))) {
    console.error(usage())
    process.exitCode = 2
  } else {
    try {
      const result = sealInstance({
        publicBriefFile: path.resolve(options.get('--brief')),
        allowedAnswersFile: path.resolve(options.get('--answers')),
        seedFixtureFile: path.resolve(options.get('--seed')),
        evaluatorSpecFile: path.resolve(options.get('--evaluator')),
        resourceFiles: parseResourceOptions(options.get('--resource') || []),
        productionSurfaceCommit: options.get('--commit'),
        instanceId: options.get('--instance-id'),
      })
      const outFile = path.resolve(options.get('--out'))
      fs.mkdirSync(path.dirname(outFile), { recursive: true })
      fs.writeFileSync(outFile, `${JSON.stringify(result.manifest, null, 2)}\n`, 'utf8')
      console.log(JSON.stringify({ ...result, outFile }, null, 2))
    } catch (error) {
      console.error(error instanceof Error ? error.message : String(error))
      process.exitCode = 1
    }
  }
}
