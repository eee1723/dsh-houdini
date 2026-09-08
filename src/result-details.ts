/** Immutable copies of returned envelopes, readable without another HOM call. */
import { createHash } from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'
import type { ExecResult } from './bridge.js'

const DIRECTORY = '.dsh-houdini-results'
const MAX_BYTES = 32 * 1024 * 1024
export const DETAIL_THRESHOLD = 12000
const hash = (bytes: string | Buffer) => createHash('sha256').update(bytes).digest('hex')

async function directory(workspace: string, create = false): Promise<string> {
  const root = await fs.realpath(workspace)
  const requested = path.join(root, DIRECTORY)
  if (create) await fs.mkdir(requested, { recursive: true })
  const actual = await fs.realpath(requested)
  const relative = path.relative(root, actual)
  if (relative !== DIRECTORY) throw new Error('result detail directory must remain inside the current workspace')
  return actual
}

export async function retainResult<T extends ExecResult>(value: T, workspace: string | null): Promise<T> {
  if (!workspace || value.details !== undefined) return value
  const bytes = JSON.stringify(value)
  if (bytes.length < DETAIL_THRESHOLD) return value
  try {
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
      read: 'houdini_query(result_ref=sha256, pointer="/evidence", offset=0, limit=6000). JSON Pointer selects a field; pages contain JSON text. No Houdini execution.' } }
  } catch (error) {
    // Retention failure must never convert a successful scene mutation into a
    // failed operation that invites a duplicate submission. Keep full rendering.
    return { ...value, details: { stored: false, error: String(error),
      fallback: 'original presentation and canonical metadata retained; do not repeat the scene operation to retry archival' } }
  }
}

export async function readResultDetail(workspace: string | null, ref: string, pointer = '', offset = 0, limit = 6000): Promise<ExecResult> {
  if (!workspace) throw new Error('result details require a current session workspace')
  if (!/^[0-9a-f]{64}$/.test(ref)) throw new Error('result_ref must be a SHA-256 returned by this tool')
  if (typeof pointer !== 'string' || pointer.length > 2048 || (pointer !== '' && !pointer.startsWith('/'))) {
    throw new Error('pointer must be an empty string or JSON Pointer beginning with /')
  }
  if (!Number.isSafeInteger(offset) || offset < 0 || !Number.isSafeInteger(limit) || limit < 1 || limit > 16000) {
    throw new Error('offset must be a nonnegative integer; limit must be 1..16000 characters')
  }
  const filename = path.join(await directory(workspace), `${ref}.json`)
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
