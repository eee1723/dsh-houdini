// Run against the exact DSH candidate used by dsh-candidate-runtime.test.py.
// This exercises present's real tool/event code with temporary local files.
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const [candidate, workspace, outsideFile] = process.argv.slice(2)
assert.ok(candidate && workspace && outsideFile, 'candidate, workspace and outside file are required')
const entry = path.join(candidate, 'node_modules/@deepseek-ai/dsh-tool-present/lib/index.js')
const { apply } = await import(pathToFileURL(entry).href)

const events = []
let tool
let resultListener
let openTurn = true
const describe = (stat) => ({ type: stat.isSymbolicLink() ? 'symlink' : stat.isFile() ? 'file' : 'other', bytes: stat.size })
const resolve = (name, cwd) => path.resolve(cwd, name)
async function metadata(name) {
  try { return describe(await fs.lstat(name)) }
  catch (error) {
    if (error?.code === 'ENOENT') return undefined
    throw error
  }
}
const ctx = {
  tools: { register(value) { tool = value } },
  fs: {
    lstat(name, { cwd }) { return metadata(resolve(name, cwd)) },
    resolve(name, { cwd }) { return resolve(name, cwd) },
    stat(name) { return metadata(name) },
  },
  sessionProjections: { stateOf() { return { lastTurn: 7, openTurnStartSeq: openTurn ? 1 : null } } },
  on(name, listener) {
    assert.equal(name, 'tools/result')
    resultListener = listener
  },
}
apply(ctx, { maxFiles: 8 })
assert.equal(tool?.name, 'present')
assert.equal(typeof resultListener, 'function')

const session = { header: { cwd: workspace }, append(type, value) { events.push({ type, value }) } }
function execution(callId) {
  return { agent: { session }, callId, signal: new AbortController().signal }
}
const files = [
  { path: '说明 空格.txt', description: 'Final text' },
  { path: '最终 图片.png', description: 'Final PNG' },
  { path: outsideFile, description: 'External final output' },
]
const good = execution('candidate-present-1')
const delivered = await tool.execute({ files }, good)
assert.deepEqual(delivered.files, files)
assert.equal(events.length, 0, 'a call result is not yet a durable delivery')
resultListener(good, { isError: false })
resultListener(good, { isError: false })
assert.deepEqual(events, [{ type: 'deliverables/presented', value: {
  turn: 7, callId: good.callId, files,
} }])

for (const invalid of [workspace, path.join(workspace, 'missing.txt')]) {
  await assert.rejects(tool.execute({ files: [{ path: invalid }] }, execution(`bad-${events.length}`)))
}
let symlinkChecked = false
const link = path.join(workspace, 'file-link.txt')
try {
  await fs.symlink(path.join(workspace, '说明 空格.txt'), link, 'file')
  symlinkChecked = true
  await assert.rejects(tool.execute({ files: [{ path: link }] }, execution('bad-link')))
} catch (error) {
  if (!['EPERM', 'EACCES', 'ENOSYS'].includes(error?.code)) throw error
  const junction = path.join(workspace, 'directory-junction')
  try {
    await fs.symlink(path.dirname(outsideFile), junction, 'junction')
    symlinkChecked = true
    await assert.rejects(tool.execute({ files: [{ path: junction }] }, execution('bad-junction')))
  } catch (junctionError) {
    if (!['EPERM', 'EACCES', 'ENOSYS'].includes(junctionError?.code)) throw junctionError
  }
}
assert.equal(events.length, 1, 'invalid paths must publish no delivery')

const failedResult = execution('candidate-present-failed-result')
await tool.execute({ files: [files[0]] }, failedResult)
resultListener(failedResult, { isError: true })
assert.equal(events.length, 1, 'failed tool result must publish no delivery')
openTurn = false
await assert.rejects(tool.execute({ files: [files[0]] }, execution('no-turn')), /open turn/)
console.log(`Candidate present: durable event, relative/absolute files, missing/directory${symlinkChecked ? '/symlink' : ''}, failed result and closed turn passed`)
