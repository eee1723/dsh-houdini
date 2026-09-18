/** Opt-in component authoring provider. Native DSH owns conversations; this plugin owns workers. */
import type {Context} from '@deepseek-ai/cordis'
import Schema from '@deepseek-ai/schemastery'
import {defineTool} from '@deepseek-ai/dsh-tools'
import {randomUUID} from 'node:crypto'
import {spawn, type ChildProcessWithoutNullStreams} from 'node:child_process'
import {boundContextSummary, createUserMessage} from '@deepseek-ai/dsh-llm'
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'
import {fileURLToPath} from 'node:url'
import type {ExecutorController} from './executor-controller.js'
import type {ExecutorRecord} from './executor-routing.js'
import {recordedExecutorIdentity} from './execution-state.js'

export const name='dsh-houdini-component-host'
export const inject=['subagents','agents','sessions','tools','houdiniTargets']
export interface Config {
  python:string; houdini:string; workerRoot:string; executorRegistry:string;
  gui:boolean; memoryMb:number; threads:number; startupTimeoutSeconds:number; maxWorkers:number;
  projectLocalWorkers:boolean;
}
export const Config:Schema<Config>=Schema.object({
  python:Schema.string().required(),houdini:Schema.string().required(),workerRoot:Schema.string().required(),
  executorRegistry:Schema.string().required(),gui:Schema.boolean().default(true),
  memoryMb:Schema.number().default(4096),threads:Schema.number().default(2),
  startupTimeoutSeconds:Schema.number().default(90),maxWorkers:Schema.number().default(2),
  // Default also upgrades existing source-preview profiles without rewriting a live Host overlay.
  projectLocalWorkers:Schema.boolean().default(true),
})
// The optional upstream service is structurally consumed: installed releases lack
// provider-selected cwd. Every child is checked before model admission regardless.
type Agent = {id:string;session:any}
type NativeSubagents = {
  registerProvider(provider:unknown):()=>void;
  startContinuable(spec:unknown):Promise<{childId:string;messageId:string}>;
}
type Worker = {parentId:string;directory:string;workspace:string;process?:ChildProcessWithoutNullStreams;
  ready?:Promise<ExecutorRecord>;record?:ExecutorRecord;exited:boolean;error?:string;
  stopRequested?:boolean;stopUnknown?:string;stopPromise?:Promise<void>;infraReported?:string}

// A completed parent turn is not a license to interrupt a child still working.
// Give the user a short continuation window, then release only idle owned workers.
export const COMPONENT_IDLE_RELEASE_MS=30_000

export function completedTurnSequence(events:readonly {type:string;seq?:number;data:unknown}[]):number|undefined {
  for(let index=events.length-1;index>=0;index--){
    const event=events[index]
    if(event.type==='turn/start')return undefined
    if(event.type==='turn/end')return (event.data as {reason?:{kind?:string}})?.reason?.kind==='completed'
      ?event.seq:undefined
  }
  return undefined
}

// Process exit and a saved idle checkpoint are different facts. In particular,
// the supervisor can exit non-zero after reclaiming a busy Houdini tree.
export function componentWorkerSnapshot(worker:Pick<Worker,'exited'|'error'|'record'|'ready'|'stopRequested'|'stopUnknown'>) {
  const checkpoint=worker.exited&&!worker.error&&!worker.stopUnknown?'saved':'unknown'
  return {workerStatus:worker.exited?'stopped':worker.stopUnknown?'stop_unknown':worker.stopRequested?'stopping'
    :worker.record?'ready':worker.ready?'starting':'reserved',checkpoint,
    error:worker.stopUnknown??worker.error??null}
}

export function componentStopOutcome(childId:string, worker:Pick<Worker,'exited'|'error'|'stopUnknown'>) {
  const checkpoint=worker.exited&&!worker.error&&!worker.stopUnknown?'saved':'unknown'
  return {childId,stopped:worker.exited,ok:checkpoint==='saved',checkpoint,
    error:worker.stopUnknown??worker.error??null,files_retained:true}
}

// A worker that failed after readiness blocks its author at the next step gate, where the
// child cannot even send a message; only the Host can tell the parent. Requested stops and
// pre-readiness startup failures already reach the parent, so neither produces a report.
export function infraReportCause(worker:Pick<Worker,'exited'|'error'|'record'|'stopRequested'>):string|undefined {
  if(!worker.record||worker.stopRequested)return undefined
  if(worker.exited)return worker.error??'Component worker exited after readiness without a stop request'
  return worker.error
}

export function componentInfraReport(childId:string,
  worker:Pick<Worker,'exited'|'error'|'record'|'stopRequested'|'stopUnknown'|'workspace'>):string|undefined {
  const cause=infraReportCause(worker)
  if(!cause)return undefined
  const snapshot=componentWorkerSnapshot(worker)
  return `Component infrastructure report (Host): child ${childId} at ${worker.workspace} is blocked — `+
    `workerStatus=${snapshot.workerStatus}, checkpoint=${snapshot.checkpoint}. Cause: ${cause}. `+
    'Files are retained, but a blocked worker is not a verified delivery and the child cannot continue on this executor. '+
    'Inspect with component_status; if the component is still needed, delegate a revision instead of waiting on this worker.'
}

/** Same delivery split as native settlement notices: wake an idle parent, steer a busy one. */
export function infraReportDelivery(status:string):'followup'|'steer' {
  return status==='idle'?'followup':'steer'
}

/** A timeout is not a saved checkpoint, even if the supervisor exits later. */
export function stopComponentWorker(worker:Worker, timeoutMs=30_000):Promise<void> {
  if(worker.stopPromise)return worker.stopPromise
  const proc=worker.process
  if(!proc||worker.exited)return Promise.resolve()
  worker.stopRequested=true
  worker.stopPromise=new Promise<void>((resolve,reject)=>{
    const onExit=()=>{clearTimeout(timer);resolve()}
    const timer=setTimeout(()=>{
      proc.off('exit',onExit)
      worker.stopUnknown='Component supervisor has not exited; checkpoint remains unknown'
      reject(new Error(worker.stopUnknown))
    },timeoutMs)
    proc.once('exit',onExit)
    try {proc.stdin.end('STOP\n')}
    catch(error){clearTimeout(timer);proc.off('exit',onExit)
      worker.stopUnknown=String(error);reject(error)}
  })
  return worker.stopPromise
}

// Host facts accompany the parent's brief, but do not replace the user's requirements.
// The path is known before model admission because every worker starts from the
// fixed workspace/component.hip contract. Keep it outside the parent-authored
// brief so a guessed path cannot masquerade as a Host assignment.
export function componentAuthorPrompt(task:string, gui:boolean,workspace?:string):string {
  const hip=workspace?path.join(workspace,'component.hip'):undefined
  const authoritative=workspace
    ?`Authoritative workspace: ${JSON.stringify(workspace)}. Authoritative current HIP: ${JSON.stringify(hip)}. `+
      `These Host facts override every workspace, HIP or export-directory path stated in the parent brief. `
    :''
  return `Component author execution facts (Host): Your executor binding and current HIP are assigned by the Host. `+
    authoritative+
    `Top-level tools in this child are houdini_query (read-only), houdini_exec (edits and checks), `+
    `houdini_job_submit/status/cancel (only for a real id returned by submit), skill/read/write/edit/todo_write/send_message. `+
    `component_delegate, component_status, component_wait and component_stop belong to the parent Host and are unavailable here; do not probe or retry them. `+
    `Houdini verbs such as tab_create, node_info, build_module, render_view and component_export are already-imported Python globals inside houdini_exec/query; `+
    `call them directly and do not import a houdini_verbs module. verb_help documents only those verbs, never top-level tools. `+
    `When argument binding reports an exact signature or next_action, follow it in the next call; do not repeat a guessed signature or catch/suppress verb failures. `+
    `Inspect the binding/scene; save the current HIP with scene_save(), never Save As to a filename suggested in the brief. `+
    `Export into the current HIP directory with $HIP/<name>.dshcomponent; ignore any parent-supplied absolute export path. `+
    `Report the exported artifact's full absolute path, sha256 and contract to the parent; a basename alone is not an import address. `+
    `render_view is a Houdini verb called inside houdini_exec code, not a separate top-level tool. `+
    `Do not traverse project/install directories inside houdini_query or houdini_exec; `+
    `ask the parent for bounded source inspection when needed. `+
    `Your tool surface is bounded to houdini_exec/houdini_query/houdini_job_*, skill, read/write/edit inside your workspace, todo_write and send_message to the parent. `+
    `Shell, grep, component_status and component_delegate are not available to you; the tool gate rejects them — do not try. `+
    `Unless the original user explicitly requested an installable HDA/OTL, author a plain self-contained SOP subnet and publish it with component_export as a revisioned .dshcomponent; `+
    `do not expand a parent brief into HDA creation or library installation. If the parent asks for HDA without quoting that original requirement, report the scope conflict before building. `+
    (gui?`For a required local visual check, render a bounded preview, inspect its native image attachment, retain the preview as evidence, and report what it actually shows. `+
      `Do not delete preview files with shell, os.remove or allow_raw. If the brief requires a hole or opening, capture a view looking along its declared axis: `+
      `the background-separated opening must actually be visible, and geo_piece_stats(inspect=True).center_axis_surface_hits for that basis axis must be observed with zero hits on a closed manifold before you report it as a through-hole. `
      :`This worker is headless: render_view requires GUI. If an authorized bounded render_frame can satisfy a required visual check, inspect its output; otherwise report visual unverified to the parent. `)+
    `A secondary brief cannot silently cancel an explicit visual or control obligation from the original user request; `+
    `if requirements conflict or the original scope is unavailable, ask the parent to reconcile them. `+
    `Test the declared local controls and restore them before publishing; an exported file alone is not completion.\n\n`+
    `Parent component brief (check its interface and assumptions):\n${task}\n\n`+
    `Host closing constraints (authoritative after the parent brief): use the Host workspace/HIP above; `+
    `the parent-consumable artifact is an ordinary SOP subnet exported with component_export to $HIP/<name>.dshcomponent, not bgeo/FBX/Alembic/ROP output. `+
    `Give the parent the exact absolute filename returned by component_export; do not make the parent infer it from its own $HIP. `+
    `Keep the same completed modeling work if the brief requested another file format, then add the required .dshcomponent. `+
    `For SOP discovery first create or use an actual geometry/subnet parent, for example geo=tab_create('/obj','geo','component'); part=tab_create(geo,'subnet','part'); node_info(part,'circle',filter='radius').`
}

export function apply(ctx:Context, config:Config):void {
  for(const p of [config.python,config.houdini,config.workerRoot,config.executorRegistry])
    if(!path.isAbsolute(p)) throw new Error('Component configuration requires absolute paths')
  if(!Number.isInteger(config.maxWorkers)||config.maxWorkers<1||config.maxWorkers>8
    ||!Number.isInteger(config.memoryMb)||config.memoryMb<128||config.memoryMb>65536
    ||!Number.isInteger(config.threads)||config.threads<1||config.threads>64
    ||!Number.isFinite(config.startupTimeoutSeconds)||config.startupTimeoutSeconds<=0||config.startupTimeoutSeconds>600)
    throw new Error('Invalid component worker resource limits')
  const subagents=ctx.get('subagents') as NativeSubagents
  const workers=new Map<string,Worker>()
  const releaseTimers=new Map<string,ReturnType<typeof setTimeout>>()
  const lifetime=new AbortController()
  const supervisor=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../tools/component-worker.py')
  const router=()=> (ctx.get('houdiniTargets') as ExecutorController).getRouter(config.executorRegistry)
  const under=(root:string,target:string)=>{
    const relative=path.relative(root,target)
    return !relative||(!relative.startsWith('..'+path.sep)&&relative!=='..'&&!path.isAbsolute(relative))
  }
  const same=(a:string,b:string)=>process.platform==='win32'?a.toLowerCase()===b.toLowerCase():a===b
  const snapshot=(parentId:string)=>{
    const children=[...workers.entries()].filter(([,worker])=>worker.parentId===parentId).map(([childId,worker])=>({
      childId,taskStatus:ctx.agents.get(childId as Parameters<typeof ctx.agents.get>[0])?.status??'not_registered',
      workspace:worker.workspace,hipPath:worker.record?.hip_path??path.join(worker.workspace,'component.hip'),
      liveSceneState:'unobserved',
      ...componentWorkerSnapshot(worker),
    }))
    return {capacity:config.maxWorkers,occupied:[...workers.values()].filter(worker=>!worker.exited).length,
      children,completion:'unverified',
      observation:'Worker/process state only. Disk size or mtime does not reveal the live unsaved Houdini scene.'}
  }

  // Best-effort, one report per distinct cause; a dropped report never blocks worker handling.
  const notifyParentInfra=(childId:string,worker:Worker)=>{
    const text=componentInfraReport(childId,worker)
    if(!text||worker.infraReported===text)return
    const parent=ctx.agents.get(worker.parentId as Parameters<typeof ctx.agents.get>[0])
    if(!parent){ctx.logger.warn(`Component ${childId} infrastructure report dropped: parent agent is gone`);return}
    worker.infraReported=text
    const message=createUserMessage({content:[{type:'text' as const,text}],
      source:{kind:'plugin',plugin:'dsh-houdini',form:'notice' as const,
        summary:boundContextSummary(`Component worker blocked (${componentWorkerSnapshot(worker).workerStatus}): ${infraReportCause(worker)}`)}})
    try {
      if(infraReportDelivery(parent.status)==='followup')parent.followup(message)
      else parent.steer(message)
    } catch(error){ctx.logger.warn(`Component ${childId} infrastructure report was not delivered: ${String(error)}`)}
  }

  const projectWorkerRoot=async(agent:Agent,signal:AbortSignal):Promise<string>=>{
    const id=recordedExecutorIdentity(agent.session.snapshotEvents())!
    const record=await router().directory.find(id)
    if(record.task_id!==agent.id||!record.hip_path)throw new Error('Assembly HIP has no writer reservation for this task')
    const observed=await router().sceneContextFor(agent.session,signal) as {ok?:boolean;result?:{hip_path?:string}}
    if(observed?.ok!==true||typeof observed.result?.hip_path!=='string')
      throw new Error('Cannot confirm the current assembly HIP; no component directory created')
    const hip=await fs.realpath(record.hip_path)
    if(!same(hip,await fs.realpath(observed.result.hip_path)))
      throw new Error('Assembly HIP changed after registration; no component directory created')
    const directory=path.dirname(hip)
    if(!same(directory,await fs.realpath(agent.session.header.cwd)))
      throw new Error('Assembly task workspace differs from its registered HIP directory; no component directory created')
    return path.join(directory,'dsh-components')
  }

  const startWorker=(childId:string,worker:Worker):Promise<ExecutorRecord>=>new Promise((resolve,reject)=>{
    const environment=Object.fromEntries(Object.entries(process.env).filter(([key])=>
      key==='HOUDINI_LICENSE_SERVER'||!/TOKEN|SECRET|PASSWORD|API_KEY|CREDENTIAL|^DSH_|^PYTHON|^HOUDINI_|^QT_|^NODE_/i.test(key)))
    const proc=spawn(config.python,[supervisor,'--executable',config.houdini,'--directory',worker.directory,
      '--registry',config.executorRegistry,'--memory-mb',String(config.memoryMb),'--threads',String(config.threads),
      '--startup-timeout',String(config.startupTimeoutSeconds),...(config.gui?['--gui']:[])],
      {cwd:path.dirname(supervisor),env:environment,windowsHide:true,stdio:'pipe'})
    worker.process=proc
    proc.stdin.on('error',error=>{
      if(worker.stopRequested)worker.stopUnknown??=String(error)
      else {worker.error=String(error);notifyParentInfra(childId,worker)}
    })
    let buffer='',diagnostics=''
    const timer=setTimeout(()=>{reject(new Error('Component startup timeout'));proc.stdin.end('STOP\n')},
      (config.startupTimeoutSeconds+10)*1000)
    proc.stderr.on('data',chunk=>{diagnostics=(diagnostics+String(chunk)).slice(-4000)})
    proc.stdout.on('data',chunk=>{
      buffer+=String(chunk)
      if(buffer.length>32768){reject(new Error('Component readiness exceeds size limit'));proc.stdin.end('STOP\n');return}
      const end=buffer.indexOf('\n')
      if(end<0)return
      try {
        const value=JSON.parse(buffer.slice(0,end))
        if(value.ok!==true||value.workspace!==worker.workspace||!value.record?.executor_id)
          throw new Error('Component readiness identity mismatch')
        worker.record=value.record
        clearTimeout(timer);resolve(value.record)
      } catch(error){clearTimeout(timer);reject(error);proc.stdin.end('STOP\n')}
    })
    proc.once('error',error=>{clearTimeout(timer);worker.error=String(error);worker.exited=true;reject(error)
      notifyParentInfra(childId,worker)})
    proc.once('exit',(code)=>{clearTimeout(timer);worker.exited=true;
      if(code!==0)worker.error=`Worker exited (${code}): ${diagnostics}`
      reject(new Error(worker.error||'Component stopped before readiness'))
      notifyParentInfra(childId,worker)})
  })

  const stop=(worker:Worker)=>stopComponentWorker(worker)
  const clearRelease=(parentId:string)=>{
    const timer=releaseTimers.get(parentId)
    if(timer)clearTimeout(timer)
    releaseTimers.delete(parentId)
  }
  const scheduleRelease=(parentId:string)=>{
    clearRelease(parentId)
    const parent=ctx.agents.get(parentId as Parameters<typeof ctx.agents.get>[0])
    if(!parent||parent.status!=='idle')return
    const completed=completedTurnSequence(parent.session.snapshotEvents())
    if(completed===undefined)return
    const hasIdle=[...workers.entries()].some(([childId,worker])=>{
      if(worker.parentId!==parentId||worker.exited||!worker.record)return false
      const child=ctx.agents.get(childId as Parameters<typeof ctx.agents.get>[0])
      return !child||child.status==='idle'
    })
    if(!hasIdle)return
    releaseTimers.set(parentId,setTimeout(()=>{
      releaseTimers.delete(parentId)
      if(lifetime.signal.aborted)return
      const latest=ctx.agents.get(parentId as Parameters<typeof ctx.agents.get>[0])
      if(!latest||latest.status!=='idle'||completedTurnSequence(latest.session.snapshotEvents())!==completed)return
      for(const [childId,worker] of workers){
        if(worker.parentId!==parentId||worker.exited||!worker.record)continue
        const child=ctx.agents.get(childId as Parameters<typeof ctx.agents.get>[0])
        if(child&&child.status!=='idle')continue
      void stop(worker).catch(error=>{worker.stopUnknown??=String(error)
        ctx.logger.warn(`Component ${childId} idle release failed: ${String(error)}`)})
      }
    },COMPONENT_IDLE_RELEASE_MS))
  }
  ctx.on('agent/status',({agent,status})=>{
    if(status==='running'){
      clearRelease(workers.get(agent.id)?.parentId??agent.id)
      return
    }
    scheduleRelease(workers.get(agent.id)?.parentId??agent.id)
  })
  ctx.on('agent/disposed',({agent})=>{
    if(workers.has(agent.id))return
    clearRelease(agent.id)
    for(const [childId,worker] of workers)if(worker.parentId===agent.id&&!worker.exited&&worker.record
      &&ctx.agents.get(childId as Parameters<typeof ctx.agents.get>[0])?.status!=='running')
      void stop(worker).catch(error=>{worker.stopUnknown??=String(error)
        ctx.logger.warn(`Component worker release after parent disposal failed: ${String(error)}`)})
  })
  ctx.effect(()=>async()=>{lifetime.abort();for(const id of releaseTimers.keys())clearRelease(id);
    await Promise.all([...workers.values()].map(stop))},
    'component worker supervision')
  ctx.effect(()=>subagents.registerProvider({name:'houdini-component',inheritsParentContext:false,
    capabilities:{agentOptions:true,outputSchema:false,depthLimit:true,toolFilter:true,persona:true},
    start:async()=>{throw new Error('Use component_delegate for continuable component authors')},
    prepareContinuable:async({sessionId,parent,signal}:{sessionId:string;parent:Agent;signal:AbortSignal})=>{
      const worker=workers.get(sessionId)
      if(!worker||worker.parentId!==parent.id)throw new Error('No Host-reserved component request')
      signal.throwIfAborted();lifetime.signal.throwIfAborted()
      worker.ready=startWorker(sessionId,worker)
      const cancel=()=>worker.process?.stdin.end('STOP\n')
      signal.addEventListener('abort',cancel,{once:true})
      lifetime.signal.addEventListener('abort',cancel,{once:true})
      try { await worker.ready }
      finally {
        signal.removeEventListener('abort',cancel)
        lifetime.signal.removeEventListener('abort',cancel)
      }
      signal.throwIfAborted()
      return {cwd:worker.workspace}
    },
  }), 'component child provider')
  ctx.on('agent/pre-step',async({agent,signal},next)=>{
    const worker=workers.get(agent.id)
    const events=agent.session.snapshotEvents() as readonly {type:string;data:unknown}[]
    const isComponent=events.some(e=>e.type==='subagent/descriptor'&&(e.data as any).provider==='houdini-component')
    if(!worker) {
      if(isComponent)throw new Error('Component worker is unavailable after Host restart; no automatic rebind or replay')
      return next()
    }
    if(worker.exited){notifyParentInfra(agent.id,worker)
      throw new Error(worker.error||'Component worker stopped; no automatic restart')}
    const policy=agent.ctx.get('sandboxPolicy') as {resolve(input:unknown):{mode:string;workspaceRoot:string}}|undefined
    const filesystem=agent.ctx.get('fs') as {sandboxMode?:string}|undefined
    if(!policy||filesystem?.sandboxMode===undefined||policy.resolve({session:agent.session}).mode!=='workspace-write')
      throw new Error('Component authors require a confining filesystem and workspace-write policy; no model request admitted')
    const record=await worker.ready!
    signal.throwIfAborted()
    await router().prepareComponent(agent,record,worker.parentId,worker.workspace,signal)
    return next()
  })
  const componentTools=new Set(['houdini_exec','houdini_query','houdini_job_submit','houdini_job_status','houdini_job_cancel',
    'skill','read','write','edit','todo_write','send_message'])
  ctx.on('tools/pre-execute',async(exec,next)=>{
    if(exec.agent&&workers.has(exec.agent.id)&&!componentTools.has(exec.name))
      throw new Error('Component author tool is outside the bounded modeling/file/message set; ask the parent to coordinate')
    return next()
  })

  ctx.tools.register(defineTool({name:'component_delegate',description:
    'Top-level Host tool (not a Houdini verb): delegate one explicitly specified component to an independent Houdini author. Preserve original visual/control obligations; include source requirements, consistent units/axis/radius/thickness, anchors, interfaces, local controls and checks. For a hole/opening, require a closed-manifold center-axis zero-hit check and an image looking along that axis. Unless the original user explicitly requests an installable HDA/OTL, commission a plain SOP subnet exported as a revisioned .dshcomponent; the parent later verifies its hash and uses component_import plus an explicit assembly connection or component_replace plan. Host supplies the child HIP: do not request a new Save As path. Local preview uses render_view inside houdini_exec when GUI is available. Returns accepted identity and absolute child workspace, not completion; does not import or modify assembly. Import the exact absolute artifact path reported by the child after it exports — the plan may reference that reported path only, never a sibling path inferred from the assembly $HIP. After delegating, end the turn and wait for the child\u2019s native message or a Host infrastructure notice instead of polling status or files; use component_status once for a capacity snapshot and component_wait for message-driven waiting; never pass component_* names to verb_help.',
    parameters:{task:{type:'string',required:true,description:'Complete bounded component brief'}},
    output:{schema:{type:'json'},render:(_args,value)=>[{type:'text' as const,text:JSON.stringify(value)}]},
    presentCall:()=>({card:'generic',title:'Delegate Houdini component',kind:'execute'}),
    async execute({task},{agent,signal}) {
      if(!agent)throw new Error('Component delegation requires an owning task')
      if(!recordedExecutorIdentity(agent.session.snapshotEvents()))throw new Error('Select the assembly executor first')
      if(workers.has(agent.id))throw new Error('Component authors cannot delegate more workers')
      if(typeof task!=='string'||!task.trim()||task.length>24000)throw new Error('Component brief must contain 1..24000 characters')
      if([...workers.values()].filter(w=>!w.exited).length>=config.maxWorkers)throw new Error('Component worker capacity reached; finish and explicitly stop a worker')
      const temp=await fs.realpath(os.tmpdir())
      const parentWorkspace=agent.session.header.cwd
      if(!parentWorkspace||under(temp,await fs.realpath(parentWorkspace)))
        throw new Error('Component and assembly workspaces must be outside the platform temp area, which DSH permits all workspace-write sessions to write')
      const requestedRoot=config.projectLocalWorkers?await projectWorkerRoot(agent,signal):config.workerRoot
      if(under(temp,requestedRoot))
        throw new Error('Component workspaces must be outside the platform temp area')
      try { await fs.mkdir(requestedRoot) }
      catch(error) { if((error as NodeJS.ErrnoException).code!=='EEXIST')throw error }
      const stat=await fs.lstat(requestedRoot)
      const root=await fs.realpath(requestedRoot)
      if(!stat.isDirectory()||stat.isSymbolicLink()||!same(root,path.resolve(requestedRoot)))
        throw new Error('Component directory must be a real directory, not a link or junction')
      if([...workers.values()].filter(w=>!w.exited).length>=config.maxWorkers)throw new Error('Component worker capacity reached')
      const id=randomUUID(),directory=path.join(root,id)
      const worker:Worker={parentId:agent.id,directory,workspace:path.join(directory,'workspace'),exited:false}
      workers.set(id,worker)
      try {
        const result=await subagents.startContinuable({childId:id,provider:'houdini-component',label:'Houdini component',
          request:{parent:agent,prompt:[{type:'text',text:componentAuthorPrompt(task,config.gui,worker.workspace)}],maxDepth:1},signal})
        return {...result,workspace:worker.workspace,hipPath:path.join(worker.workspace,'component.hip'),
          status:'accepted',completion:'unverified'}
      } catch(error){await stop(worker);throw error}
    },
  }))
  ctx.tools.register(defineTool({name:'component_status',description:
    'Top-level parent Host tool (not a Houdini verb): read one current parent-owned component worker capacity/state snapshot without starting work. Use component_wait for later synchronization, never repeat status or poll files. Ready/idle does not certify component completion. Component children cannot call this tool.',
    parameters:{},
    output:{schema:{type:'json'},render:(_args,value)=>[{type:'text' as const,text:JSON.stringify(value)}]},
    presentCall:()=>({card:'generic',title:'Component worker status',kind:'read'}),
    async execute(_args,{agent}) {
      if(!agent)throw new Error('Component status requires an owning task')
      return snapshot(agent.id)
    },
  }))
  ctx.tools.register(defineTool({name:'component_wait',description:
    'Top-level parent Host tool (not a Houdini verb): wait through the API for up to 30 seconds until an owned component task/worker state changes. This replaces repeated component_status and filesystem polling. A timeout is only a quiet wait; completion still comes from the native child message and must be verified.',
    parameters:{timeoutSeconds:{type:'number',description:'Finite wait from 1 to 30 seconds (default 30)'}},
    output:{schema:{type:'json'},render:(_args,value)=>[{type:'text' as const,text:JSON.stringify(value)}]},
    presentCall:()=>({card:'generic',title:'Wait for Houdini components',kind:'read'}),
    async execute({timeoutSeconds=30},{agent,signal}) {
      if(!agent)throw new Error('Component wait requires an owning task')
      if(!Number.isFinite(timeoutSeconds)||timeoutSeconds<1||timeoutSeconds>30)
        throw new Error('timeoutSeconds must be a finite number from 1 to 30')
      const started=Date.now(),initial=snapshot(agent.id)
      const signature=JSON.stringify(initial.children.map(({childId,taskStatus,workerStatus,checkpoint,error})=>
        ({childId,taskStatus,workerStatus,checkpoint,error})))
      if(initial.children.length===0||initial.children.every(child=>child.workerStatus==='stopped'))
        return {...initial,changed:false,timedOut:false,waitedMs:0}
      const deadline=started+timeoutSeconds*1000
      while(Date.now()<deadline){
        await new Promise(resolve=>setTimeout(resolve,Math.min(250,deadline-Date.now())))
        signal.throwIfAborted()
        const current=snapshot(agent.id)
        const currentSignature=JSON.stringify(current.children.map(({childId,taskStatus,workerStatus,checkpoint,error})=>
          ({childId,taskStatus,workerStatus,checkpoint,error})))
        if(currentSignature!==signature)return {...current,changed:true,timedOut:false,waitedMs:Date.now()-started}
      }
      return {...snapshot(agent.id),changed:false,timedOut:true,waitedMs:Date.now()-started}
    },
  }))
  ctx.tools.register(defineTool({name:'component_stop',description:
    'Top-level parent Host tool (not a Houdini verb): stop an owned component worker after finishing its task, before claiming final completion. Check ok and checkpoint=saved; stopped alone means only process exit. A busy/failed shutdown returns checkpoint=unknown with its error. Does not delete files or import a component. Completed idle parent turns also trigger a 30-second guarded release fallback; a released child cannot resume on the same executor.',
    parameters:{childId:{type:'string',required:true}},
    output:{schema:{type:'json'},render:(_args,value)=>[{type:'text' as const,text:JSON.stringify(value)}]},
    presentCall:()=>({card:'generic',title:'Stop Houdini component',kind:'execute'}),
    async execute({childId},{agent}) {
      const worker=workers.get(childId)
      if(!agent||!worker||worker.parentId!==agent.id)throw new Error('Not a component owned by this parent')
      const child=ctx.agents.get(childId as Parameters<typeof ctx.agents.get>[0])
      if(child&&child.status!=='idle')throw new Error('Component task is still active; interrupt/wait for the child before stopping its worker')
      try {await stop(worker)}
      catch(error){worker.stopUnknown??=String(error)}
      return componentStopOutcome(childId,worker)
    },
  }))
}
