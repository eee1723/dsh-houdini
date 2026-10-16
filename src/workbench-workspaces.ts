/** Retire empty plugin scratch registrations through the native DSH registry.
 * No directory/session deletion, title-based ownership, or workspace database.
 */
import type {Context} from '@deepseek-ai/cordis'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import type {ExecutorDirectory} from './executor-routing.js'

const key=(value:string)=>process.platform==='win32'?path.resolve(value).toLowerCase():path.resolve(value)

export async function scratchRoots():Promise<string[]> {
  const roots=[path.join(os.tmpdir(),'dsh-houdini/workspaces')]
  const filename=process.env.DSH_HOUDINI_WORKBENCH_CONTEXT
  if(filename) {
    const context=JSON.parse(await fs.readFile(filename,'utf8'))
    if(context.workbench!==true||typeof context.root!=='string'||!path.isAbsolute(context.root))throw Error('Invalid workbench scratch scope')
    roots.push(path.join(context.root,'workspaces/unsaved'),path.join(context.root,'workspaces'))
  }
  return roots
}

export async function pruneScratchWorkspaces(ctx:Context,directory:ExecutorDirectory,keep:readonly string[]=[],roots?:readonly string[]) {
  const registry=ctx.get('workspaceRegistry')
  // Older runtimes retain the empty row. Never replace the native conditional
  // mutation with a check-then-delete that races a newly attached conversation.
  if(!registry||!('deleteEmpty' in registry)||typeof registry.deleteEmpty!=='function')return []
  const scope=roots??await scratchRoots(),removed:string[]=[]
  for(const workspace of registry.list()) {
    const name=path.basename(workspace.path)
    if(!scope.some(root=>key(path.dirname(workspace.path))===key(root))
      ||!/^untitled-\d+-[a-z0-9_-]+$|^unsaved-[0-9a-f]{32}$/.test(name)
      ||!(workspace.title===name||/^未保存工程 \d+$/.test(workspace.title))
      ||workspace.sessionIds.length||keep.some(value=>key(value)===key(workspace.path)))continue
    let info
    try {info=await fs.lstat(workspace.path)}
    catch(error) {if((error as NodeJS.ErrnoException).code==='ENOENT')continue;throw error}
    if(!info.isDirectory()||info.isSymbolicLink()||key(await fs.realpath(workspace.path))!==key(workspace.path)
      ||(await fs.readdir(workspace.path)).length)continue
    // Unknown/stale registered targets remain protected; absence is never
    // inferred from a failed health request. Later Open/Save can retire the row.
    if((await directory.list()).some(record=>record.state==='registered'&&record.workspace_path
      &&key(record.workspace_path)===key(workspace.path)))continue
    if(await registry.deleteEmpty(workspace.id,workspace.path,workspace.title))removed.push(workspace.id)
  }
  return removed
}
