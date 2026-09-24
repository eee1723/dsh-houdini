import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import crypto from 'node:crypto'
import { fileURLToPath } from 'node:url'

export const suiteRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

const inside = (root, target) => target.startsWith(root + path.sep)
const hashFile = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')

function resolveFile(root, relative) {
  if (typeof relative !== 'string' || !relative || path.isAbsolute(relative)) throw new Error(`invalid relative file: ${relative}`)
  const absolute = path.resolve(root, relative)
  if (!inside(root, absolute) || !fs.statSync(absolute).isFile()) throw new Error(`missing or escaped file: ${relative}`)
  if (!inside(root, fs.realpathSync(absolute))) throw new Error(`source symlink escapes suite: ${relative}`)
  return absolute
}

function parseJson(file) { return JSON.parse(fs.readFileSync(file, 'utf8')) }

export function validateSuite(root = suiteRoot) {
  root = fs.realpathSync(root)
  const manifest = parseJson(resolveFile(root, 'manifest.json'))
  if (manifest.schemaVersion !== 1 || manifest.suiteId !== 'product-modeling-dev-v1' || manifest.status !== 'development') throw new Error('invalid suite manifest')
  if (!Array.isArray(manifest.cases) || manifest.cases.length < 6) throw new Error('suite needs six development cases')
  resolveFile(root, manifest.reviewResultSchema)
  const ids = new Set()
  for (const item of manifest.cases) {
    if (!/^[a-z0-9-]+$/.test(item.id) || ids.has(item.id)) throw new Error(`invalid or repeated case id: ${item.id}`)
    ids.add(item.id)
    if (!['drawing-understanding', 'reference-to-model', 'guided-reference-to-model', 'focused-module', 'parameter-change', 'text-to-model'].includes(item.kind)) throw new Error(`invalid case kind: ${item.id}`)
    const brief = resolveFile(root, item.public?.brief)
    if (!brief.includes(`${path.sep}public${path.sep}`) || fs.readFileSync(brief, 'utf8').trim().length < 25) throw new Error(`invalid public brief: ${item.id}`)
    if (!Array.isArray(item.public?.attachments)) throw new Error(`invalid attachments: ${item.id}`)
    for (const attachment of item.public.attachments) {
      const file = resolveFile(root, attachment)
      if (!file.includes(`${path.sep}public-assets${path.sep}`)) throw new Error(`attachment is not public: ${item.id}`)
      if (path.extname(file).toLowerCase() !== '.png' || !fs.readFileSync(file).subarray(0, 8).equals(Buffer.from('89504e470d0a1a0a', 'hex'))) throw new Error(`attachment is not a PNG: ${item.id}`)
    }
    const evaluator = resolveFile(root, item.evaluator)
    if (!evaluator.includes(`${path.sep}evaluator-only${path.sep}`)) throw new Error(`evaluator file is public: ${item.id}`)
    const checklist = parseJson(evaluator)
    if (checklist.caseId !== item.id || !Array.isArray(checklist.criteria) || !checklist.criteria.length || !checklist.requiredEvidence || typeof checklist.requiredEvidence !== 'object') throw new Error(`invalid evaluator checklist: ${item.id}`)
    for (const origin of ['agentSubmitted', 'reviewerProduced', 'source']) {
      if (!Array.isArray(checklist.requiredEvidence[origin]) || checklist.requiredEvidence[origin].some(value => typeof value !== 'string' || !value)) throw new Error(`invalid ${origin} evidence: ${item.id}`)
    }
    if (!checklist.requiredEvidence.reviewerProduced.length || !checklist.requiredEvidence.agentSubmitted.length) throw new Error(`independent evidence missing: ${item.id}`)
    const criterionIds = new Set()
    for (const criterion of checklist.criteria) {
      if (typeof criterion.id !== 'string' || !criterion.id || criterionIds.has(criterion.id) || typeof criterion.expectation !== 'string' || !criterion.expectation) throw new Error(`invalid criterion: ${item.id}`)
      criterionIds.add(criterion.id)
    }
    if (!Array.isArray(item.dependsOn)) throw new Error(`invalid dependencies: ${item.id}`)
  }
  for (const item of manifest.cases) {
    for (const dependency of item.dependsOn) if (!ids.has(dependency) || dependency === item.id) throw new Error(`invalid dependency: ${item.id}`)
    if (item.kind === 'parameter-change' && item.dependsOn.length !== 1) throw new Error(`parameter change needs one baseline case: ${item.id}`)
  }
  return { root, manifest }
}

export function prepareRun({ caseId, output, baselineHip, root = suiteRoot }) {
  const { root: sourceRoot, manifest } = validateSuite(root)
  const item = manifest.cases.find(entry => entry.id === caseId)
  if (!item) throw new Error(`unknown case: ${caseId}`)
  if (item.kind === 'parameter-change' && !baselineHip) throw new Error('parameter-change requires --baseline-hip from the completed build run')
  if (item.kind !== 'parameter-change' && baselineHip) throw new Error('--baseline-hip is only valid for parameter-change')
  const destination = path.resolve(output ?? path.join(os.tmpdir(), 'dsh-product-modeling-dev-v1', `${caseId}-${crypto.randomUUID()}`))
  if (output && !path.isAbsolute(output)) throw new Error('--out must be an absolute path')
  const repositoryRoot = path.resolve(sourceRoot, '..', '..')
  if (destination === repositoryRoot || inside(repositoryRoot, destination)) throw new Error('run output must be outside the repository')
  let existingParent = path.dirname(destination)
  while (!fs.existsSync(existingParent)) existingParent = path.dirname(existingParent)
  const realParent = fs.realpathSync(existingParent)
  if (realParent === repositoryRoot || inside(repositoryRoot, realParent)) throw new Error('run output parent resolves inside the repository')
  if (fs.existsSync(destination)) throw new Error('run output already exists')
  const files = []
  const baseline = baselineHip ? path.resolve(baselineHip) : null
  const baselineExtension = baseline ? path.extname(baseline) : null
  if (baseline) {
    if (!path.isAbsolute(baselineHip) || !['.hip', '.hiplc', '.hipnc'].includes(baselineExtension.toLowerCase()) || !fs.existsSync(baseline) || !fs.statSync(baseline).isFile()) throw new Error('baseline must be an existing absolute .hip/.hiplc/.hipnc file')
    const realBaseline = fs.realpathSync(baseline)
    if (realBaseline === sourceRoot || inside(sourceRoot, realBaseline)) throw new Error('baseline must come from a prior run, not the suite source')
  }
  fs.mkdirSync(destination, { recursive: true })
  try {
    const copy = (from, relative) => {
      const target = path.join(destination, relative)
      fs.mkdirSync(path.dirname(target), { recursive: true })
      fs.copyFileSync(from, target)
      files.push({ path: relative.replaceAll('\\', '/'), sha256: hashFile(target) })
    }
    copy(resolveFile(sourceRoot, item.public.brief), 'brief.md')
    for (const attachment of item.public.attachments) copy(resolveFile(sourceRoot, attachment), `attachments/${path.basename(attachment)}`)
    if (baseline) copy(baseline, `work${baselineExtension}`)
    const task = { schemaVersion: 1, suiteId: manifest.suiteId, caseId: item.id, kind: item.kind, files }
    fs.writeFileSync(path.join(destination, 'task.json'), JSON.stringify(task, null, 2) + '\n')
    return { destination, task }
  } catch (error) {
    // Creation failed before handing the directory to an agent. Remove only this new directory.
    fs.rmSync(destination, { recursive: true, force: true })
    throw error
  }
}
