import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import {fileURLToPath} from 'node:url'

import {projectDeliveryAudit} from '../../../tools/delivery-audit.mjs'

function fileEvidence(file) {
  if (!file || !fs.existsSync(file)) return null
  const stat = fs.statSync(file)
  if (!stat.isFile()) return null
  return {path: path.resolve(file), bytes: stat.size,
    sha256: crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')}
}

function auditEvents(trace) {
  return (trace.steps ?? []).flatMap((step, index) => {
    if (!step.canonical) return []
    const callId = `trace-step-${step.index ?? index}`
    return [
      {type: 'tool/call', seq: index * 2 + 1, data: {callId, name: step.tool}},
      {type: 'tool/result', seq: index * 2 + 2,
        data: {message: {source: {callId}}, meta: {canonical: step.canonical}}},
    ]
  })
}

/** Delivery evidence only. Geometry, controls and author claims need separate review. */
export function verifyFinalDelivery({trace, expectedPath, registered, submittedPath,
  reopen, reopenProcess}) {
  if (!trace || !path.isAbsolute(expectedPath) || !registered
      || !path.isAbsolute(submittedPath)) {
    throw new Error('trace, actual worker registration and absolute expected/submitted paths are required')
  }
  const runtimeId = registered.runtime_id
  const audit = projectDeliveryAudit(auditEvents(trace), {expectedFinalPath: expectedPath})
  const receipt = audit?.delivery?.last_save ?? null
  const target = fileEvidence(expectedPath)
  const submitted = fileEvidence(submittedPath)
  const reviewCopy = reopen && path.isAbsolute(reopen.source ?? '')
    ? fileEvidence(reopen.source) : null
  let status = 'final_not_saved'
  if (path.basename(expectedPath).toLowerCase() !== 'final.hip'
      || String(registered.hip_path ?? '').replace(/\\/g, '/').toLowerCase()
        !== expectedPath.replace(/\\/g, '/').toLowerCase()) status = 'final_target_not_reserved'
  else if (!runtimeId) status = 'runtime_mismatch'
  else if (audit?.runtime_id !== runtimeId) status = 'runtime_mismatch'
  else if ((trace.unresolvedRequests?.length ?? 0) || audit?.unresolved_requests?.length
      || audit?.pending_calls?.length) status = 'unknown_request'
  else if (trace.terminal?.reason !== 'completed') status = 'run_incomplete'
  else if (audit.delivery.status !== 'save_receipt_reopen_unverified') status = audit.delivery.status
  else if (!target || target.bytes !== receipt.bytes) status = 'saved_target_missing_or_changed'
  else if (!submitted || submitted.sha256 !== target.sha256) status = 'submitted_copy_mismatch'
  else if (!reopen || reopenProcess?.exitCode !== 0 || reopenProcess?.timedOut === true)
    status = 'reopen_unverified'
  else if (!reviewCopy || reviewCopy.sha256 !== submitted.sha256
      || reopen.sourceUnchanged !== true || reopen.sourceShaBefore !== submitted.sha256
      || reopen.sourceShaAfter !== submitted.sha256) status = 'reopen_copy_mismatch'
  else status = 'delivered'
  return {status, runtimeId, registeredPath: registered.hip_path ?? null,
    expectedPath: path.resolve(expectedPath),
    receipt, target, submitted, reviewCopy,
    reopen: reopen ? {source: reopen.source ?? null, sourceShaBefore: reopen.sourceShaBefore ?? null,
      sourceShaAfter: reopen.sourceShaAfter ?? null, sourceUnchanged: reopen.sourceUnchanged === true,
      exitCode: reopenProcess?.exitCode ?? null} : null,
    boundary: 'This checks the observed save, matching bytes and independent reopen. Unobserved external edits and product quality remain outside this verdict.'}
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = Object.fromEntries(process.argv.slice(2).map((value, index, all) =>
    value.startsWith('--') ? [value.slice(2), all[index + 1]] : null).filter(Boolean))
  const required = ['trace', 'expected', 'ready', 'submitted']
  if (required.some(key => !args[key])) {
    throw new Error('usage: node verify-final-delivery.mjs --trace evidence.json --expected worker/final.hip --ready worker/ready.json --submitted author/final.hip [--reopen review.json --reopen-result process.json]')
  }
  const evidence = JSON.parse(fs.readFileSync(args.trace, 'utf8'))
  if (evidence.traces?.length !== 1) throw new Error('expected exactly one extracted trace')
  const ready = JSON.parse(fs.readFileSync(args.ready, 'utf8'))
  if (ready.ok !== true || !ready.record) throw new Error('worker readiness has no successful registration')
  const result = verifyFinalDelivery({trace: evidence.traces[0], expectedPath: args.expected,
    registered: ready.record, submittedPath: args.submitted,
    reopen: args.reopen ? JSON.parse(fs.readFileSync(args.reopen, 'utf8')) : null,
    reopenProcess: args['reopen-result']
      ? JSON.parse(fs.readFileSync(args['reopen-result'], 'utf8')) : null})
  process.stdout.write(JSON.stringify(result, null, 2) + '\n')
}
