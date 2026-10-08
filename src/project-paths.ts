/** Project directory roles share one shipped contract with the Houdini allocator.
 * This module resolves a destination, never creates a project or moves assets. */
import fs from 'node:fs/promises'
import {readFileSync} from 'node:fs'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {randomBytes} from 'node:crypto'

const contract = JSON.parse(readFileSync(new URL('../houdini/project-layout.json', import.meta.url), 'utf8')) as {
  schemaVersion: number; directories: Record<string, {path: string; lifecycle: string}>
}
if (contract.schemaVersion !== 1) throw Error('Unsupported project directory contract')
const repository = fileURLToPath(new URL('..', import.meta.url))
const samePath = (a:string,b:string) => process.platform === 'win32'
  ? path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase() : path.resolve(a) === path.resolve(b)
const portable = (value:string) => value.replace(/\\/g, '/')
const inside = (root:string, target:string) => {
  const relative = path.relative(root,target)
  return relative === '' || (relative !== '..' && !relative.startsWith('..'+path.sep) && !path.isAbsolute(relative))
}

export interface ImageOutputOptions {
  output?: string
  output_policy?: 'managed' | 'explicit'
  purpose?: 'reference' | 'texture'
}

export interface ProjectArtifact {
  role: string; purpose: 'reference' | 'texture'; lifecycle: string
  output_policy: 'managed' | 'explicit'; actual_path: string
  project_root: string | null; managed_root: string | null; hip_path: string | null
  hip_relative_path: string | null
  observed_identity: {executor_id: string | null; runtime_id: string | null; observed_at: number | null} | null
}

function directoryRole(role:string) {
  const entry=contract.directories[role]
  if (!entry || typeof entry.path !== 'string' || typeof entry.lifecycle !== 'string'
      || !entry.path || path.isAbsolute(entry.path) || entry.path.includes('\\')
      || entry.path.split('/').some(part=>!part || part==='.' || part==='..' || part.includes(':')))
    throw Error('Invalid project directory role: '+role)
  return entry
}

function basename(value:string) {
  if (!value.trim() || value !== path.basename(value) || /[\\/:<>"|?*`$\x00-\x1f\x7f]/.test(value)
      || value==='.' || value==='..' || /[. ]$/.test(value)
      || /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i.test(value))
    throw Error("Managed image output accepts a safe basename only; use output_policy='explicit' for a chosen path")
  return value
}

/** Check every managed component without following a redirected child directory.
 * The project root itself is already canonical; explicit destinations use DSH policy. */
export async function verifyManagedImageDirectory(artifact:ProjectArtifact):Promise<void> {
  if (artifact.output_policy !== 'managed') return
  const root=artifact.project_root!, managed=artifact.managed_root!
  if (!samePath(await fs.realpath(root),root) || !inside(root,managed))
    throw Error('Managed image project directory changed after observation')
  let current=root
  for (const part of path.relative(root,managed).split(path.sep)) {
    current=path.join(current,part)
    let info
    try {info=await fs.lstat(current)} catch(error:any) {if(error.code==='ENOENT') continue;throw error}
    if (!info.isDirectory() || info.isSymbolicLink() || !samePath(await fs.realpath(current),current))
      throw Error('Managed image directory is redirected or is not a directory; use the visible HIP tree')
  }
}

/** The observation is performed once, before a paid request. Save As during image
 * generation never retargets this result. Explicit files need no Houdini at all. */
export async function imageOutputLocation(options:ImageOutputOptions,
  observe?:()=>Promise<{value:unknown; executorId?:string}>):Promise<{filename:string;artifact:ProjectArtifact}> {
  const policy=options.output_policy ?? 'managed', purpose=options.purpose ?? 'reference'
  if (!['managed','explicit'].includes(policy)) throw Error('output_policy must be managed or explicit')
  if (!['reference','texture'].includes(purpose)) throw Error('purpose must be reference or texture')
  if (options.output !== undefined && (typeof options.output !== 'string' || !options.output.trim()))
    throw Error('output must be a nonempty filename when provided')
  const role=purpose==='texture'?'texture':'reference_generated', entry=directoryRole(role)
  const artifact:ProjectArtifact={role,purpose,lifecycle:entry.lifecycle,output_policy:policy,actual_path:'',
    project_root:null,managed_root:null,hip_path:null,hip_relative_path:null,observed_identity:null}
  if (policy==='explicit') {
    if (!options.output) throw Error("Explicit image output requires a destination; relative paths use the DSH workspace")
    return {filename:options.output,artifact}
  }
  const label=basename(options.output ?? (purpose==='texture'?'texture.png':'reference.png'))
  if (!observe) throw Error("Managed image output requires a current named Houdini project; use output_policy='explicit' for offline work")
  const observation=await observe(), envelope:any=observation.value, scene=envelope?.result
  if (envelope?.ok!==true || !scene || scene.hip_is_new!==false
      || typeof scene.hip_path!=='string' || !path.isAbsolute(scene.hip_path))
    throw Error("Managed image output requires a current named Houdini project; use output_policy='explicit' for unsaved or offline work")
  const root=await fs.realpath(path.dirname(scene.hip_path)), repo=await fs.realpath(repository)
  if (inside(repo,root)) throw Error('Image output cannot be written into the plugin repository; choose a project destination')
  const managed=path.join(root,...entry.path.split('/'))
  if (scene.project_layout !== undefined) {
    const layout=scene.project_layout
    if (layout?.schema_version!==1 || layout.available!==true || typeof layout.hip_path!=='string'
        || !samePath(layout.hip_path,scene.hip_path) || typeof layout.project_root!=='string'
        || !samePath(layout.project_root,root) || typeof layout.directories?.[role]!=='string'
        || !samePath(layout.directories[role],managed))
      throw Error('Houdini project directory observation disagrees with the loaded directory contract; reload matching plugin components')
  }
  const extension=path.extname(label), filename=path.join(managed,
    `${label.slice(0,label.length-extension.length)}_${randomBytes(8).toString('hex')}${extension}`)
  Object.assign(artifact,{actual_path:portable(filename),project_root:portable(root),managed_root:portable(managed),
    hip_path:portable(scene.hip_path),hip_relative_path:portable(path.relative(root,filename)),
    observed_identity:{executor_id:observation.executorId ?? null,
      runtime_id:typeof scene.runtime_id==='string'?scene.runtime_id:null,
      observed_at:typeof scene.observed_at==='number'?scene.observed_at:null}})
  await verifyManagedImageDirectory(artifact)
  return {filename,artifact}
}
