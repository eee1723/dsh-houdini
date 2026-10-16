/** Pure executor-identity fold, reused by single and shared Host routing. */
import type {Context} from '@deepseek-ai/cordis'
import type {Session} from '@deepseek-ai/dsh-session'
import type {} from '@deepseek-ai/dsh-session-projection'
import type {} from '@deepseek-ai/dsh-session-projection/types'
import {z} from 'zod'
import {executionCall,executionResult,houdiniSourceMessages} from './dsh-adapter.js'
import type {SessionEvent} from './execution-history.js'
import {sectionData} from './prompt-data.js'

const TARGET_SECTION='dsh-houdini:executor-binding'
const LIVE=new Set(['houdini_exec','houdini_inspect','houdini_job_submit','houdini_job_status','houdini_job_cancel'])
const ID=/^[0-9a-f]{32}$/
const WarningCounts={capture_id:z.string().regex(ID),original_chars:z.number().int().nonnegative(),
  omitted_chars:z.number().int().nonnegative(),truncated:z.boolean()}
const WarningDetails=z.discriminatedUnion('status',[
  z.object({...WarningCounts,status:z.literal('stored'),stored:z.literal(true),
    sha256:z.string().regex(/^[0-9a-f]{64}$/),path:z.string().min(1),bytes:z.number().int().positive(),
    format:z.literal('returned_bridge_envelope_json')}),
  z.object({...WarningCounts,status:z.literal('unavailable'),stored:z.literal(false),error:z.string()}),
])
const Recovery=z.object({schema:z.literal(2),kind:z.literal('executor_recovery'),
  previous_executor:z.string().regex(ID),executor_id:z.string().regex(ID),
  operation_id:z.string().regex(ID),checkpoint_id:z.string().regex(ID),scene_id:z.string().regex(ID),
  scene_epoch:z.string().regex(ID),runtime_id:z.string().regex(ID),hip_path:z.string().min(1),
  restored_nodes:z.number().int().nonnegative(),previous_work:z.unknown().optional(),
  unrestored_nodes:z.array(z.object({path:z.string(),reason:z.string()})).optional(),
  load_warnings:z.array(z.string()).optional(),
  load_warning_details:WarningDetails.optional(),
  user_choice:z.record(z.string(),z.unknown()).optional()})
export type RecoveryBinding=z.infer<typeof Recovery>
const Project=z.object({hipPath:z.string().nullable(),hipIsNew:z.boolean().nullable(),needsReview:z.boolean(),
  executorId:z.string().nullable(),sceneEpoch:z.string().nullable(),label:z.string().nullable()})
type Project=z.infer<typeof Project>
const REVIEW_PROJECT:Project={hipPath:null,hipIsNew:null,needsReview:true,executorId:null,sceneEpoch:null,label:null}
const State=z.object({identity:z.string().nullable(),conflict:z.boolean(),
  invalid:z.string().nullable(),bindingRecorded:z.boolean(),pending:z.record(z.string(),z.string().nullable()),
  queuedBindings:z.record(z.string(),z.string()),
  queuedProjects:z.record(z.string(),z.boolean()),
  hasOperations:z.boolean(),
  executors:z.array(z.string()),recovery:Recovery.nullable(),recoverySeq:z.number(),
  project:Project.nullable(),projectObservedAt:z.number(),projectSequence:z.number()})
type State=z.infer<typeof State>

declare module '@deepseek-ai/dsh-session-projection/types' {
  interface SessionProjectionStateMap {houdiniExecutorIdentity:State}
  interface SessionProjectionMap {houdiniExecutorIdentity:Project|null}
}

function add(state:State,id:unknown):State {
  if (typeof id!=='string'||!ID.test(id)) return {...state,invalid:'Invalid recorded Houdini executor identity'}
  if (state.identity && state.identity!==id) return {...state,conflict:true}
  return state.identity===id ? state : {...state,identity:id,executors:[...state.executors,id],
    project:{hipPath:null,hipIsNew:null,needsReview:false,executorId:id,sceneEpoch:null,label:null},projectObservedAt:0,projectSequence:0}
}

function projectObservation(state:State,value:any,observedAt:number,sequence=0):State {
  if(!state.identity||state.invalid||state.conflict||value?.executor_id!==state.identity
    ||typeof value.hip_path!=='string'||!value.hip_path||!Number.isFinite(observedAt)||!Number.isFinite(sequence)
    ||observedAt<state.projectObservedAt||observedAt===state.projectObservedAt&&sequence<state.projectSequence)return state
  const hipIsNew=typeof value.hip_is_new==='boolean'?value.hip_is_new:null
  const sceneEpoch=value.scene_epoch??value.scene_recovery?.scene_epoch??state.project?.sceneEpoch??null
  const label=hipIsNew===true?(typeof value.project_label==='string'?value.project_label:state.project?.label??null):null
  const project=state.project&&state.project.hipPath===value.hip_path&&state.project.hipIsNew===hipIsNew
    &&state.project.sceneEpoch===sceneEpoch&&state.project.label===label&&state.project.executorId===state.identity?state.project:
    {hipPath:value.hip_path,hipIsNew,needsReview:false,executorId:state.identity,sceneEpoch,label}
  return {...state,project,projectObservedAt:observedAt,projectSequence:sequence}
}

function projectMessage(state:State,message:any,event:SessionEvent):State {
  const sections=(message.source.sections??[]).filter((section:any)=>['dsh-houdini:workspace-open','dsh-houdini:workspace-directory'].includes(section.name))
  if(!sections.length)return state
  if(state.queuedProjects[message.id]) {
    if(event.type!=='user/message')return state
    const remaining={...state.queuedProjects};delete remaining[message.id]
    return {...state,queuedProjects:remaining}
  }
  let next=state
  if(event.type==='agent/inbox/spliced')next={...next,queuedProjects:{...next.queuedProjects,[message.id]:true}}
  for(const section of sections) {
    const value=sectionData(section)
    next=projectObservation(next,{...value,executor_id:value?.executor_id??next.identity},(event.time??0)/1000)
  }
  return next
}

export const executorIdentityProjection={
  key:'houdiniExecutorIdentity' as const,stateSchema:State,stateVersion:9,
  init:():State=>({identity:null,conflict:false,invalid:null,bindingRecorded:false,pending:{},queuedBindings:{},
    executors:[],recovery:null,recoverySeq:0,hasOperations:false,project:null,projectObservedAt:0,projectSequence:0,queuedProjects:{}}),
  wire:{viewSchema:Project.nullable(),view:(state:State)=>state.invalid||state.conflict?REVIEW_PROJECT:state.project},
  apply(state:State,event:SessionEvent):State {
    const messages=houdiniSourceMessages(event)
    if (messages.length) {
      let next=state
      for(const message of messages) {
        const sections=(message.source.sections??[]).filter((section:any)=>section.name===TARGET_SECTION)
        if(!sections.length) {next=projectMessage(next,message,event);continue}
        const signature=JSON.stringify(sections.map((section:any)=>section.text))
        const queued=next.queuedBindings[message.id]
        if(queued!==undefined) {
          if(queued!==signature)return {...next,invalid:'Queued Houdini binding message changed before consumption'}
          if(event.type==='user/message') {
            const remaining={...next.queuedBindings};delete remaining[message.id]
            next={...next,queuedBindings:remaining}
          }
          continue
        }
        if(event.type==='agent/inbox/spliced') {
          if(typeof message.id!=='string'||!message.id)return {...next,invalid:'Queued Houdini binding requires a native message identity'}
          next={...next,queuedBindings:{...next.queuedBindings,[message.id]:signature}}
        }
        for (const section of sections) {
          let value:any
          try {value=JSON.parse(section.text.slice(section.text.indexOf('\n')+1))}
          catch {return {...next,invalid:'Malformed recorded Houdini executor binding'}}
          if(value?.kind==='executor_recovery') {
            if(event.type==='agent/inbox/spliced')return {...next,invalid:'Recovery transitions require a committed native message'}
            const parsed=Recovery.safeParse(value)
            if(!parsed.success||next.invalid||next.conflict||parsed.data.previous_executor!==next.identity)
              return {...next,invalid:'Invalid Houdini recovery transition'}
            const recovery=parsed.data
            next={...next,identity:recovery.executor_id,bindingRecorded:true,recovery,recoverySeq:event.seq??0,
              executors:[...new Set([...next.executors,recovery.executor_id])],projectObservedAt:0,projectSequence:0}
            next=projectObservation(next,{...recovery,hip_is_new:false},(event.time??0)/1000)
            continue
          }
          if (value?.schema!==1 || value?.kind!=='executor_binding')
            return {...next,invalid:'Invalid recorded Houdini executor binding'}
          if(value.previous_executor!==undefined) {
            if(next.hasOperations||next.recovery||next.identity!==value.previous_executor||!ID.test(value.executor_id))
              return {...next,invalid:'Only an unexecuted task can change its initial target'}
            next={...next,identity:value.executor_id,bindingRecorded:true,executors:[...new Set([...next.executors,value.executor_id])],
              project:{hipPath:null,hipIsNew:null,needsReview:false,executorId:value.executor_id,sceneEpoch:null,label:null},projectObservedAt:0,projectSequence:0}
            continue
          }
          next=add({...next,bindingRecorded:true},value.executor_id)
        }
        next=projectMessage(next,message,event)
      }
      return next
    }
    const call=executionCall(event)
    if(call&&(call.name==='run_code'||typeof call.name==='string'&&call.name.startsWith('houdini_')&&!['houdini_help','houdini_resource'].includes(call.name)))
      state={...state,hasOperations:true}
    if (call && LIVE.has(call.name)) return {...state,pending:{...state.pending,[call.callId]:state.identity}}
    const result=executionResult(event)
    if (!result || !Object.hasOwn(state.pending,result.callId)) return state
    const expected=state.pending[result.callId]
    const pending={...state.pending}
    delete pending[result.callId]
    const next={...state,pending}
    const identity=result.value?.execution?.executor_id ?? result.value?.requestReceipt?.executor_id
    if(identity!==undefined&&expected&&expected!==state.identity)
      return identity===expected?next:{...next,conflict:true}
    return identity===undefined ? next : projectObservation(add(next,identity),result.value?.execution,
      result.value?.execution?.observed_at,result.value?.execution?.sequence??0)
  },
}

export function executorBindingState(state:State):{identity:string|undefined;bindingRecorded:boolean} {
  if (state.invalid) throw new Error(state.invalid)
  if (state.conflict) throw new Error('Houdini task requires recovery: history records more than one executor identity')
  return {identity:state.identity??undefined,bindingRecorded:state.bindingRecorded}
}

export function foldExecutorBinding(events:readonly SessionEvent[]) {
  return executorBindingState(foldExecutorState(events))
}

export function foldExecutorState(events:readonly SessionEvent[]) {
  let state=executorIdentityProjection.init()
  for (const event of events) state=executorIdentityProjection.apply(state,event)
  executorBindingState(state)
  return state
}

/** Read-only artifacts are authorized by a valid native recovery event, including historical ones. */
export function recordedLoadWarningPath(events:readonly SessionEvent[],ref:string):string|undefined {
  let state=executorIdentityProjection.init(),path:string|undefined
  for(const event of events){
    state=executorIdentityProjection.apply(state,event)
    const detail=state.recovery?.load_warning_details
    if(!state.invalid&&!state.conflict&&detail?.status==='stored'&&detail.stored&&detail.sha256===ref)path=detail.path
  }
  return path
}

export function registerExecutorIdentityProjection(ctx:Context):void {
  ctx.sessionProjections.register(executorIdentityProjection)
}

export function projectedExecutorBindingState(ctx:Context,session:Session) {
  const state=ctx.get('sessionProjections')?.stateOf(session,'houdiniExecutorIdentity')
  if (!state) throw new Error('Houdini executor identity projection unavailable')
  return executorBindingState(state)
}

export function projectedExecutorIdentity(ctx:Context,session:Session):string|undefined {
  return projectedExecutorBindingState(ctx,session).identity
}
