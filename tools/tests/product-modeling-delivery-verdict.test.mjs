import assert from 'node:assert/strict'
import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import {verifyFinalDelivery} from '../../evaluation/product-modeling-dev-v1/evaluator-only/verify-final-delivery.mjs'

const root = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-final-verdict-'))
const expectedPath = path.join(root, 'worker', 'final.hip')
const submittedPath = path.join(root, 'author', 'final.hip')
fs.mkdirSync(path.dirname(expectedPath))
fs.mkdirSync(path.dirname(submittedPath))
fs.writeFileSync(expectedPath, 'named initial scene')
fs.writeFileSync(submittedPath, 'named initial scene')
const runtimeId = 'isolated-runtime'
const registered = {hip_path: expectedPath, runtime_id: runtimeId}
const trace = () => ({steps: [], unresolvedRequests: [], terminal: {reason: 'completed'}})
function addStep(value, {save = false, edit = false, editAfterSave = false} = {}) {
  const sequence = value.steps.length + 1
  value.steps.push({index: sequence, tool: 'houdini_exec', canonical: {
    ok: true, transaction: {status: 'committed'},
    requestReceipt: {request_ref: `request-${sequence}`, status: 'done'},
    execution: {runtime_id: runtimeId, sequence, observed_at: sequence,
      hip_path: expectedPath, impact: {attempted: edit || editAfterSave,
        nodes: [], last_edit_ledger_index: editAfterSave ? 2 : edit ? 1 : null}},
    verbs: save ? [{verb: 'scene_save', ok: true,
      result: {path: expectedPath, bytes: fs.statSync(expectedPath).size}}] : [],
  }})
}
const check = (value, extra = {}) => verifyFinalDelivery({trace: value, expectedPath,
  registered, submittedPath, ...extra})

let value = trace()
addStep(value)
assert.equal(check(value).status, 'final_not_saved',
  'the worker creates final.hip before any author save')
assert.equal(check(value, {registered: {...registered, hip_path: path.join(root, 'worker', 'component.hip')}}).status,
  'final_target_not_reserved')

value = trace()
addStep(value, {edit: true})
fs.writeFileSync(expectedPath, 'completed model')
fs.writeFileSync(submittedPath, 'completed model')
addStep(value, {save: true})
addStep(value, {edit: true})
assert.equal(check(value).status, 'save_precedes_recorded_edit')

value = trace()
addStep(value, {save: true, editAfterSave: true})
assert.equal(check(value).status, 'save_precedes_recorded_edit',
  'an edit after save inside one exec also invalidates delivery')

value = trace()
addStep(value, {edit: true})
addStep(value, {save: true})
assert.equal(check(value).status, 'reopen_unverified')
const sha256 = crypto.createHash('sha256').update(fs.readFileSync(submittedPath)).digest('hex')
const reopened = {source: path.join(root, 'review', 'final-copy.hip'),
  sourceShaBefore: sha256, sourceShaAfter: sha256, sourceUnchanged: true}
fs.mkdirSync(path.dirname(reopened.source))
fs.copyFileSync(submittedPath, reopened.source)
const reopenProcess = {exitCode: 0, timedOut: false}
assert.equal(check(value, {reopen: reopened, reopenProcess}).status, 'delivered')
fs.writeFileSync(reopened.source, 'stale review copy')
assert.equal(check(value, {reopen: reopened, reopenProcess}).status, 'reopen_copy_mismatch')
fs.copyFileSync(submittedPath, reopened.source)

fs.writeFileSync(submittedPath, 'different bytes')
assert.equal(check(value, {reopen: reopened, reopenProcess}).status, 'submitted_copy_mismatch')
fs.writeFileSync(submittedPath, 'completed model')
value.unresolvedRequests.push({request_ref: 'unknown', status: 'unknown_transport'})
assert.equal(check(value, {reopen: reopened, reopenProcess}).status, 'unknown_request')

console.log('final HIP delivery verdict: initial file, save ordering, copy, reopen and unknown request passed')
