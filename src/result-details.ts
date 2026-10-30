/** Immutable copies of returned envelopes, readable without another HOM call. */
import { createHash } from 'node:crypto'
import fs from 'node:fs/promises'
import {readFileSync} from 'node:fs'
import path from 'node:path'
import type { ExecResult } from './bridge.js'
import {executionCall,executionResult,isHoudiniTool} from './dsh-adapter.js'
import type {SessionEvent} from './execution-history.js'
import {RESULT_DIRECTORY} from './project-paths.js'

const DIRECTORY = RESULT_DIRECTORY
const policy=JSON.parse(readFileSync(new URL('../houdini/result-detail-policy.json',import.meta.url),'utf8'))
if(policy.schemaVersion!==1||['maxArchiveBytes','detailThresholdChars','loadWarningPreviewBytes'].some(key=>
  !Number.isSafeInteger(policy[key])||policy[key]<=0)||policy.loadWarningPreviewBytes<128)throw Error('Unsupported result detail policy')
const MAX_BYTES:number = policy.maxArchiveBytes
export const DETAIL_THRESHOLD:number = policy.detailThresholdChars
const hash = (bytes: string | Buffer) => createHash('sha256').update(bytes).digest('hex')

/** A session move changes cwd, not the location of its original returned artifacts. */
export function recordedResultPath(events:readonly SessionEvent[],ref:string):string|undefined {
  const calls=new Map<string,string>()
  let retained:string|undefined
  for(const event of events) {
    const call=executionCall(event)
    if(call&&(isHoudiniTool(call.name)||call.name==='job_output'))calls.set(call.callId,call.name)
    const result=executionResult(event)
    if(!result||result.isError||!calls.has(result.callId)
      ||calls.get(result.callId)==='job_output'&&result.producer!=='live-job')continue
    const value=result.value,isolated=calls.get(result.callId)==='houdini_isolated'&&value?.kind==='isolated-houdini'
    // Isolated archives keep their producer-declared run and execution name.
    // Never register a lookalike path from arbitrary authored result data.
    const executions=isolated
      ?[value.report?.result,value.progress].flatMap(report=>report
        ?[{execution:report.builder,archive:'builder.json'},
          ...(Array.isArray(report.checks)?report.checks.map((check:any)=>({execution:check.execution,archive:`check-${check.id}.json`})):[])] : [])
      :[{execution:value,archive:undefined}]
    for(const {execution,archive} of executions){
      const detail=execution?.details
      if(detail?.stored!==true||detail.sha256!==ref||detail.format!=='returned_bridge_envelope_json'
        ||typeof detail.path!=='string')continue
      if(isolated&&(typeof value.run_directory!=='string'||!path.isAbsolute(value.run_directory)
        ||path.dirname(detail.path)!==path.join(value.run_directory,'executions')
        ||path.basename(detail.path)!==archive))continue
      retained=detail.path
    }
  }
  return retained
}

async function directory(workspace: string, create = false): Promise<string> {
  const root = await fs.realpath(workspace)
  let current = root
  // Check each parent before creating the next one. A redirected artifact
  // root must not cause even an empty directory to be written elsewhere.
  for (const part of DIRECTORY.split('/')) {
    if (!part || part === '.' || part === '..' || /[\\:]/.test(part)) throw new Error('invalid result directory')
    current = path.join(current, part)
    if (create) {
      try { await fs.mkdir(current) }
      catch (error) { if ((error as NodeJS.ErrnoException).code !== 'EEXIST') throw error }
    }
    const info = await fs.lstat(current)
    if (!info.isDirectory() || info.isSymbolicLink() || path.relative(current, await fs.realpath(current)) !== '')
      throw new Error('result detail directory must remain inside the current workspace')
  }
  return current
}

export async function retainResult<T extends ExecResult>(value: T, workspace: string | null,
  filePolicyMode?: () => string | undefined): Promise<T> {
  if (!workspace || value.details !== undefined) return value
  const bytes = JSON.stringify(value)
  if (bytes.length < DETAIL_THRESHOLD) return value
  try {
    // Archival is optional presentation work, so a read-only policy (or a
    // failed policy lookup) keeps the complete result inline without writes.
    if (filePolicyMode?.() === 'read-only') throw new Error('DSH file policy is read-only; no workspace result archive was written')
    if (Buffer.byteLength(bytes) > MAX_BYTES) throw new Error('returned envelope exceeds result retention budget')
    const dir = await directory(workspace, true)
    const digest = hash(bytes)
    const filename = path.join(dir, `${digest}.json`)
    try { await fs.writeFile(filename, bytes, { flag: 'wx' }) }
    catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'EEXIST') throw error
      // Do not trust preexisting files or symlinks at a content-addressed name.
      const stat = await fs.lstat(filename)
      if (!stat.isFile() || stat.size > MAX_BYTES || hash(await fs.readFile(filename)) !== digest) {
        throw new Error('existing result artifact does not match its content hash')
      }
    }
    return { ...value, details: { stored: true, sha256: digest, path: filename,
      bytes: Buffer.byteLength(bytes), format: 'returned_bridge_envelope_json',
      read: 'houdini_resource(kind="result", ref=sha256, pointer="/evidence", offset=0, limit=6000). JSON Pointer selects a field; pages contain JSON text. No Houdini execution.' } }
  } catch (error) {
    // Retention failure must never convert a successful scene mutation into a
    // failed operation that invites a duplicate submission. Keep full rendering.
    return { ...value, details: { stored: false, error: String(error),
      fallback: 'original presentation and canonical metadata retained; do not repeat the scene operation to retry archival' } }
  }
}

export async function readResultDetail(workspace: string | null, ref: string, pointer = '', offset = 0, limit = 6000, retainedPath?:string): Promise<ExecResult> {
  if (!workspace&&!retainedPath) throw new Error('result details require a current session workspace or a recorded artifact')
  if (!/^[0-9a-f]{64}$/.test(ref)) throw new Error('result_ref must be a SHA-256 returned by this tool')
  if (typeof pointer !== 'string' || pointer.length > 2048 || (pointer !== '' && !pointer.startsWith('/'))) {
    throw new Error('pointer must be an empty string or JSON Pointer beginning with /')
  }
  if (!Number.isSafeInteger(offset) || offset < 0 || !Number.isSafeInteger(limit) || limit < 1 || limit > 16000) {
    throw new Error('offset must be a nonnegative integer; limit must be 1..16000 characters')
  }
  if(retainedPath&&(!path.isAbsolute(retainedPath)||(path.basename(retainedPath)!==`${ref}.json`
    &&path.basename(retainedPath)!=='builder.json'&&!/^check-[a-z0-9_-]{1,48}\.json$/.test(path.basename(retainedPath)))))
    throw Error('recorded result path does not match its reference or declared isolated archive')
  const filename = retainedPath??path.join(await directory(workspace!), `${ref}.json`)
  const stat = await fs.lstat(filename)
  if (!stat.isFile() || stat.size > MAX_BYTES) throw new Error('invalid result artifact')
  const bytes = await fs.readFile(filename)
  if (hash(bytes) !== ref) throw new Error('result artifact hash mismatch; content is not trusted')
  let selected: unknown = JSON.parse(bytes.toString('utf8'))
  if (pointer) for (const encoded of pointer.slice(1).split('/')) {
    if (/~(?:[^01]|$)/.test(encoded)) throw new Error('invalid JSON Pointer escape')
    const key = encoded.replace(/~1/g, '/').replace(/~0/g, '~')
    if (selected === null || typeof selected !== 'object' || !Object.hasOwn(selected, key)
        || (Array.isArray(selected) && !/^(0|[1-9]\d*)$/.test(key))) throw new Error('JSON Pointer field not found')
    selected = (selected as Record<string, unknown>)[key]
  }
  const text = JSON.stringify(selected, null, 2)
  if (offset > text.length) throw new Error('offset exceeds selected JSON text length')
  const end = Math.min(offset + limit, text.length)
  return { ok: true, stdout: '', stderr: '', result: { result_ref: ref, pointer, offset,
    total_chars: text.length, next_offset: end < text.length ? end : null,
    format: 'json_text_page', text: text.slice(offset, end),
    provenance: 'Historical returned envelope, hash checked; not a live scene observation or edit permission.' } }
}
