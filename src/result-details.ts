/** Immutable copies of returned envelopes, readable without another HOM call. */
import { createHash } from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'
import type { ExecResult } from './bridge.js'
import {executionCall,executionResult,isHoudiniTool,returnedExecutions} from './dsh-adapter.js'
import type {SessionEvent} from './execution-history.js'
import {RESULT_DIRECTORY} from './project-paths.js'
import {DETAIL_THRESHOLD,RESULT_DETAIL_POLICY} from './result-policy.js'
export {DETAIL_THRESHOLD}

const DIRECTORY = RESULT_DIRECTORY
const MAX_BYTES:number = RESULT_DETAIL_POLICY.maxArchiveBytes
const hash = (bytes: string | Buffer) => createHash('sha256').update(bytes).digest('hex')

export type NativeResultSpill={locator:string;bytes:number;retrievalHint:string}
type ResultReference={sha256:string;bytes:number;format:'returned_bridge_envelope_json'}&(
  {stored:true;path:string;storage?:undefined}|{stored:true;path?:undefined;storage:'dsh-spill';locator:string;retrievalHint:string}
  |{stored:false;path?:undefined;storage:'unavailable';recovery:string;request_ref?:string})

/** A session move changes cwd, not the location of its original returned artifacts. */
export function recordedResultReference(events:readonly SessionEvent[],ref:string):ResultReference|undefined {
  const calls=new Map<string,string>()
  let retained:ResultReference|undefined
  for(const event of events) {
    const call=executionCall(event)
    if(call&&(isHoudiniTool(call.name)||call.name==='job_output'))calls.set(call.callId,call.name)
    const result=executionResult(event)
    if(!result||result.isError||!result.recorded&&!calls.has(result.callId)
      ||calls.get(result.callId)==='job_output'&&result.producer!=='live-job')continue
    for(const {execution,archive,runDirectory,domain} of returnedExecutions(result.tool??calls.get(result.callId)!,result.value)){
      const detail=execution?.details
      if(detail?.sha256!==ref||detail.format!=='returned_bridge_envelope_json')continue
      if(detail.stored===false&&detail.storage==='unavailable') {
        retained={...detail,...(typeof execution.requestReceipt?.request_ref==='string'?{request_ref:execution.requestReceipt.request_ref}:{})}
        continue
      }
      if(detail.stored!==true)continue
      if(detail.storage==='dsh-spill') {
        if(typeof detail.locator==='string'&&typeof detail.retrievalHint==='string')retained=detail
        continue
      }
      if(typeof detail.path!=='string')continue
      if(domain==='isolated'&&(typeof runDirectory!=='string'||!path.isAbsolute(runDirectory)
        ||path.dirname(detail.path)!==path.join(runDirectory,'executions')
        ||path.basename(detail.path)!==archive))continue
      retained=detail
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
  filePolicyMode?: () => string | undefined,spill?: (content:string)=>Promise<NativeResultSpill>): Promise<T> {
  if (value.details !== undefined && typeof value.details==='object' && value.details!==null
    && !Array.isArray(value.details) && value.details.stored===true) return value
  const bytes = JSON.stringify(value)
  if (bytes.length < DETAIL_THRESHOLD) return value
  const digest=hash(bytes),byteLength=Buffer.byteLength(bytes)
  let archiveError:unknown
  try {
    if(!workspace)throw new Error('No session workspace for a long-term result archive')
    if (filePolicyMode?.() === 'read-only') throw new Error('DSH file policy is read-only; no workspace result archive was written')
    if (byteLength > MAX_BYTES) throw new Error('returned envelope exceeds workspace result archive budget')
    const dir = await directory(workspace, true)
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
      bytes: byteLength, format: 'returned_bridge_envelope_json',
      read: 'houdini_resource(kind="result", ref=sha256, pointer="/evidence", offset=0, limit=6000). JSON Pointer selects a field; pages contain JSON text. No Houdini execution.' } }
  } catch (error) {
    archiveError=error
  }
  try {
    if(!spill)throw new Error('DSH native spill storage is unavailable')
    const saved=await spill(bytes)
    // The locator is opaque. Its backend owns retrieval and lifetime; never
    // interpret it as a local path or copy the result into another ledger.
    return {...value,details:{stored:true,storage:'dsh-spill',sha256:digest,bytes:byteLength,
      format:'returned_bridge_envelope_json',locator:saved.locator,retrievalHint:saved.retrievalHint,
      archive_error:String(archiveError),read:'Full original JSON is stored by DSH. Use the opaque locator with its native retrievalHint; workspace JSON Pointer paging is unavailable for this backend.'}}
  }catch(error){
    // Complete structured return values remain available to the current tool
    // caller. Browser/history copies stay bounded even when every store fails.
    // No successful scene edit becomes a failure or is submitted again.
    return { ...value, details: { stored: false,storage:'unavailable',sha256:digest,bytes:byteLength,format:'returned_bridge_envelope_json',
      error:String(archiveError),spill_error:String(error),
      recovery:'Complete original is not durably retained. The immediate structured return is complete; the original Bridge request may still be recoverable through houdini_request. Do not resubmit scene code. Persistent/display facts omit bulk values.' } }
  }
}

/** A native spill locator has no generic read API. Return its exact backend
 * guidance rather than assuming a filesystem path, lifetime or JSON reader. */
export function resultRetrievalResource(ref:string,reference:ResultReference):ExecResult {
  if(reference.storage==='unavailable')return {ok:false,stdout:'',stderr:'',error:'The original result was not durably retained. This lookup cannot return its complete data; do not repeat the scene operation.',result:{result_ref:ref,
    status:'durable_original_unavailable',sha256:reference.sha256,bytes:reference.bytes,
    recovery:reference.recovery,...(reference.request_ref?{request_ref:reference.request_ref}:{}),
    scope:'No complete durable original is available here. The original Bridge request may still retain it; availability is not guaranteed. Do not resubmit scene code.'}}
  if(reference.storage!=='dsh-spill')throw Error('Result is not a native spill')
  return {ok:true,stdout:'',stderr:'',result:{result_ref:ref,status:'native_retrieval_required',
    format:'original_json_native_spill',bytes:reference.bytes,sha256:reference.sha256,
    locator:reference.locator,retrievalHint:reference.retrievalHint,
    scope:'The complete original JSON is stored by DSH. Use the backend retrievalHint; JSON Pointer selection was not applied. Retention lifetime belongs to the native backend. Historical data grants no scene edit permission.'}}
}

async function resultDocument(workspace:string|null,ref:string,retainedPath?:string):Promise<unknown> {
  if (!workspace&&!retainedPath) throw new Error('result details require a current session workspace or a recorded artifact')
  if (!/^[0-9a-f]{64}$/.test(ref)) throw new Error('result_ref must be a SHA-256 returned by this tool')
  if(retainedPath&&(!path.isAbsolute(retainedPath)||(path.basename(retainedPath)!==`${ref}.json`
    &&path.basename(retainedPath)!=='builder.json'&&!/^check-[a-z0-9_-]{1,48}\.json$/.test(path.basename(retainedPath)))))
    throw Error('recorded result path does not match its reference or declared isolated archive')
  const filename = retainedPath??path.join(await directory(workspace!), `${ref}.json`)
  const stat = await fs.lstat(filename)
  if (!stat.isFile() || stat.size > MAX_BYTES) throw new Error('invalid result artifact')
  const bytes = await fs.readFile(filename)
  if (hash(bytes) !== ref) throw new Error('result artifact hash mismatch; content is not trusted')
  return JSON.parse(bytes.toString('utf8'))
}

export function pointerKeys(pointer:string):string[] {
  if (typeof pointer !== 'string' || pointer.length > 2048 || (pointer !== '' && !pointer.startsWith('/'))) {
    throw new Error('pointer must be an empty string or JSON Pointer beginning with /')
  }
  return pointer===''?[]:pointer.slice(1).split('/').map(encoded=>{
    if (/~(?:[^01]|$)/.test(encoded)) throw new Error('invalid JSON Pointer escape')
    return encoded.replace(/~1/g, '/').replace(/~0/g, '~')
  })
}

export function pointerValue(document:unknown,keys:string[]):unknown {
  let selected=document
  for (const key of keys) {
    if (selected === null || typeof selected !== 'object' || !Object.hasOwn(selected, key)
        || (Array.isArray(selected) && !/^(0|[1-9]\d*)$/.test(key))) throw new Error('JSON Pointer field not found')
    selected = (selected as Record<string, unknown>)[key]
  }
  return selected
}

const provenance='Historical returned envelope, hash checked; not a live scene observation or edit permission.'

/** One document/hash verification, multiple exact values. No partial JSON or
 * interpretation of arbitrary authored result fields as execution verdicts. */
export async function readResultSelection(workspace:string|null,ref:string,select:string[],limit=6000,retainedPath?:string):Promise<ExecResult> {
  if(!Array.isArray(select)||select.length<1||select.length>16||new Set(select).size!==select.length)
    throw Error('select must contain 1..16 unique JSON Pointers')
  if(!Number.isSafeInteger(limit)||limit<1||limit>16000)throw Error('limit must be 1..16000 characters')
  const keys=select.map(pointerKeys),document=await resultDocument(workspace,ref,retainedPath)
  let remaining=limit
  const items=select.map((pointer,index)=>{
    let value:unknown
    try {value=pointerValue(document,keys[index])}
    catch {return {pointer,status:'missing',error:'JSON Pointer field not found'}}
    const chars=JSON.stringify(value).length
    if(chars>remaining)return {pointer,status:'requires_pagination',total_chars:chars,read:{pointer,offset:0,limit}}
    remaining-=chars
    return {pointer,status:'available',value}
  })
  return {ok:true,stdout:'',stderr:'',result:{result_ref:ref,format:'json_selection',items,
    selected_value_chars:limit-remaining,provenance} as any}
}

export async function readResultDetail(workspace: string | null, ref: string, pointer = '', offset = 0, limit = 6000, retainedPath?:string): Promise<ExecResult> {
  const keys=pointerKeys(pointer)
  if (!Number.isSafeInteger(offset) || offset < 0 || !Number.isSafeInteger(limit) || limit < 1 || limit > 16000) {
    throw new Error('offset must be a nonnegative integer; limit must be 1..16000 characters')
  }
  const selected=pointerValue(await resultDocument(workspace,ref,retainedPath),keys)
  const text = JSON.stringify(selected, null, 2)
  if (offset > text.length) throw new Error('offset exceeds selected JSON text length')
  const end = Math.min(offset + limit, text.length)
  return { ok: true, stdout: '', stderr: '', result: { result_ref: ref, pointer, offset,
    total_chars: text.length, next_offset: end < text.length ? end : null,
    format: 'json_text_page', text: text.slice(offset, end),
    provenance } }
}
