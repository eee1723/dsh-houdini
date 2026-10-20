/** Pure executor-identity fold, reused by single and shared Host routing. */
import type {Context} from '@deepseek-ai/cordis'
import type {Session} from '@deepseek-ai/dsh-session'
import type {} from '@deepseek-ai/dsh-session-projection'
import type {} from '@deepseek-ai/dsh-session-projection/types'
import {z} from 'zod'
import {executionCall,executionResult,houdiniSourceMessages} from './dsh-adapter.js'
import type {SessionEvent} from './execution-history.js'
import {sectionData} from './prompt-data.js'
import {HOUDINI_SCENE_TOOLS} from './tool-catalog.js'
import {transitionExecutionFacts,initExecutionFacts,executionOutstanding,executionFactsSchema} from './execution-facts.js'

const TARGET_SECTION='dsh-houdini:executor-binding'
const LIVE=HOUDINI_SCENE_TOOLS
const ID=/^[0-9a-f]{32}$/
export const targetSnapshotSchema=z.object({executor_id:z.string().regex(ID),runtime_id:z.string().regex(ID),
  scene_epoch:z.string().regex(ID),scene_id:z.string().regex(ID).nullable(),registration_id:z.string().regex(ID),
  hip_path:z.string().min(1),hip_is_new:z.boolean(),workspace_path:z.string().optional()})
export type TargetSnapshot=z.infer<typeof targetSnapshotSchema>
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
  sceneId:z.string().nullable(),executorId:z.string().nullable(),sceneEpoch:z.string().nullable(),label:z.string().nullable(),
  runtimeId:z.string().nullable().optional(),selectionExplicit:z.boolean().optional(),target:targetSnapshotSchema.nullable().optional()})
type Project=z.infer<typeof Project>
const REVIEW_PROJECT:Project={hipPath:null,hipIsNew:null,needsReview:true,sceneId:null,executorId:null,sceneEpoch:null,label:null}
const State=z.object({identity:z.string().nullable(),conflict:z.boolean(),
  invalid:z.string().nullable(),bindingRecorded:z.boolean(),pending:z.record(z.string(),z.string().nullable()),
  queuedBindings:z.record(z.string(),z.string()),
  queuedProjects:z.record(z.string(),z.string()),
  hasOperations:z.boolean(),
  selectedTarget:targetSnapshotSchema.nullable(),selectionRecorded:z.boolean(),selectionRevision:z.number(),
  pendingSelections:z.record(z.string(),z.number()),
  executors:z.array(z.string()),recovery:Recovery.nullable(),recoverySeq:z.number(),
  project:Project.nullable(),projectObservedAt:z.number(),projectSequence:z.number(),
  execution:executionFactsSchema,
  sceneObservation:z.object({lastUserKey:z.string().optional(),key:z.string().optional(),text:z.string().optional()})})
type State=z.infer<typeof State>
export type ExecutorIdentityState=State

declare module '@deepseek-ai/dsh-session-projection/types' {
  interface SessionProjectionStateMap {houdiniExecutorIdentity:State}
  interface SessionProjectionMap {houdiniExecutorIdentity:Project|null}
}

function add(state:State,id:unknown):State {
  if (typeof id!=='string'||!ID.test(id)) return {...state,invalid:'Invalid recorded Houdini executor identity'}
  if (state.identity && state.identity!==id) return {...state,conflict:true}
  return state.identity===id ? state : {...state,identity:id,executors:[...state.executors,id],
    project:{hipPath:null,hipIsNew:null,needsReview:true,sceneId:null,executorId:id,sceneEpoch:null,label:null},projectObservedAt:0,projectSequence:0}
}

function projectObservation(state:State,value:any,observedAt:number,sequence=0):State {
  if(!state.identity||state.invalid||state.conflict||value?.executor_id!==state.identity
    ||typeof value.hip_path!=='string'||!value.hip_path||!Number.isFinite(observedAt)||!Number.isFinite(sequence)
    ||observedAt<state.projectObservedAt||observedAt===state.projectObservedAt&&sequence<state.projectSequence)return state
  const hipIsNew=typeof value.hip_is_new==='boolean'?value.hip_is_new:null
  // Scene identity is not inheritable by file copy. Facts carry forward only
  // while the HIP path is unchanged; a path change without an observed identity
  // yields sceneId null (needsReview) instead of the previous file's identity.
  const hipUnchanged=state.project?.hipPath===value.hip_path
  const observedSceneId=value.scene_id??value.scene_recovery?.scene_id??null
  const sceneId=observedSceneId??(hipUnchanged?state.project?.sceneId??null:null)
  if(sceneId!==null&&(typeof sceneId!=='string'||!ID.test(sceneId)))return state
  const observedEpoch=value.scene_epoch??value.scene_recovery?.scene_epoch??null
  const sceneEpoch=observedEpoch??(hipUnchanged?state.project?.sceneEpoch??null:null)
  const label=hipIsNew===true?(typeof value.project_label==='string'?value.project_label:state.project?.label??null):null
  // No verified scene identity means the association is not yet trustworthy;
  // a new unsaved file is not exempt when it still lacks an observed identity.
  const needsReview=!sceneId
  const project=state.project&&state.project.hipPath===value.hip_path&&state.project.hipIsNew===hipIsNew
    &&state.project.sceneId===sceneId&&state.project.sceneEpoch===sceneEpoch&&state.project.label===label
    &&state.project.needsReview===needsReview&&state.project.executorId===state.identity?state.project:
    {...(state.project??{}),hipPath:value.hip_path,hipIsNew,needsReview,sceneId,executorId:state.identity,sceneEpoch,label}
  return {...state,project,projectObservedAt:observedAt,projectSequence:sequence}
}

function projectMessage(state:State,message:any,event:SessionEvent):State {
  const sections=(message.source.sections??[]).filter((section:any)=>['dsh-houdini:workspace-open','dsh-houdini:workspace-directory'].includes(section.name))
  if(!sections.length)return state
  if(state.selectionRecorded)return state // Routing choices no longer come from workspace/recovery notices.
  const signature=JSON.stringify(sections.map((section:any)=>section.text))
  const queued=state.queuedProjects[message.id]
  if(queued!==undefined) {
    if(queued!==signature)return {...state,invalid:'Queued Houdini project message changed before consumption'}
    // Sections were already folded at splice time under the splice timestamp;
    // re-applying at consume would let stale queued context override newer
    // observations. Consumption only releases the queue entry, never the facts.
    if(event.type!=='user/message')return state
    const remaining={...state.queuedProjects};delete remaining[message.id]
    return {...state,queuedProjects:remaining}
  }
  let next=state
  if(event.type==='agent/inbox/spliced') {
    if(typeof message.id!=='string'||!message.id)return {...next,invalid:'Queued Houdini project requires a native message identity'}
    next={...next,queuedProjects:{...next.queuedProjects,[message.id]:signature}}
  }
  for(const section of sections) {
    const value=sectionData(section)
    next=projectObservation(next,{...value,executor_id:value?.executor_id??next.identity},(event.time??0)/1000)
  }
  return next
}

export const executorIdentityProjection={
  key:'houdiniExecutorIdentity' as const,stateSchema:State,stateVersion:13,
  init:():State=>({identity:null,conflict:false,invalid:null,bindingRecorded:false,pending:{},queuedBindings:{},
    executors:[],recovery:null,recoverySeq:0,hasOperations:false,project:null,projectObservedAt:0,projectSequence:0,queuedProjects:{},
    selectedTarget:null,selectionRecorded:false,selectionRevision:0,pendingSelections:{},execution:initExecutionFacts(),sceneObservation:{}}),
  wire:{viewSchema:Project.nullable(),view:(state:State)=>state.invalid||state.conflict?REVIEW_PROJECT:state.project},
  apply(state:State,event:SessionEvent):State {
    return transitionExecutorState(state,event).state
  },
}

/** The transient delta is used only by one-shot historical readers. */
export function transitionExecutorState(state:State,event:SessionEvent) {
    let next=applyIdentity(state,event)
    const transition=transitionExecutionFacts(state.execution,event,state,next)
    if(transition.facts!==next.execution)next={...next,execution:transition.facts}
    if(event.type==='user/message') {
      const message=event.data
      if(message?.source?.kind==='user')next={...next,sceneObservation:{...next.sceneObservation,lastUserKey:String(message.id??event.seq??JSON.stringify(message))}}
      if(['runtime-context','dsh-houdini','plugin:dsh-houdini'].includes(message?.source?.kind))
        for(const section of message.source.sections??[])if(section.name==='dsh-houdini:scene-context') {
          const value=sectionData(section)
          if(typeof value?.user_message_id==='string')next={...next,sceneObservation:{...next.sceneObservation,key:value.user_message_id,text:section.text}}
        }
    }
    return {state:next,...(transition.delta?{delta:transition.delta}:{}),...(transition.reset?{reset:transition.reset}:{})}
}

function applyIdentity(state:State,event:SessionEvent):State {
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
          // A message can carry both binding and workspace sections; the project
          // side must still verify/release its own queue entry for this message.
          next=projectMessage(next,message,event)
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
          if(value?.schema===3&&value.kind==='target_selection') {
            const parsed=targetSnapshotSchema.nullable().safeParse(value.target)
            if(!parsed.success)return {...next,invalid:'Invalid recorded Houdini target selection'}
            const target=parsed.data
            const revision=next.selectionRevision+1
            let pending=next.pending,pendingSelections=next.pendingSelections
            if(target&&!next.selectionRecorded&&!next.identity) {
              // First tool use selects its scene after DSH records the call.
              // Only calls issued while truly unbound belong to this choice;
              // an earlier bound call can never follow a later target change.
              pending={...pending};pendingSelections={...pendingSelections}
              for(const [callId,identity] of Object.entries(next.pending))if(identity===null
                &&next.pendingSelections[callId]===next.selectionRevision) {
                pending[callId]=target.executor_id;pendingSelections[callId]=revision
              }
            }
            next={...next,identity:target?.executor_id??null,bindingRecorded:Boolean(target),invalid:null,conflict:false,
              selectedTarget:target,selectionRecorded:true,selectionRevision:revision,pending,pendingSelections,recovery:null,recoverySeq:event.seq??0,
              executors:target?[...new Set([...next.executors,target.executor_id])]:next.executors,
              project:target?{hipPath:target.hip_path,hipIsNew:target.hip_is_new,needsReview:!target.scene_id,
                sceneId:target.scene_id,executorId:target.executor_id,sceneEpoch:target.scene_epoch,label:null,
                runtimeId:target.runtime_id,selectionExplicit:true,target}:null,projectObservedAt:(event.time??0)/1000,projectSequence:0}
            continue
          }
          if(value?.kind==='executor_recovery') {
            const parsed=Recovery.safeParse(value)
            if(!parsed.success||next.invalid||next.conflict||(!next.selectionRecorded&&parsed.data.previous_executor!==next.identity))
              return {...next,invalid:'Invalid Houdini recovery transition'}
            const recovery=parsed.data
            if(next.selectionRecorded) {
              // Ownership restoration is not another target selection. It may
              // describe only the already selected scene, never retarget it.
              const target=next.selectedTarget
              if(target&&next.executors.includes(recovery.previous_executor)&&target.executor_id===recovery.executor_id
                &&target.runtime_id===recovery.runtime_id&&target.scene_epoch===recovery.scene_epoch&&target.scene_id===recovery.scene_id)
                next={...next,recovery}
              continue
            }
            if(event.type==='agent/inbox/spliced')return {...next,invalid:'Recovery transitions require a committed native message'}
            next={...next,identity:recovery.executor_id,bindingRecorded:true,recovery,recoverySeq:event.seq??0,
              executors:[...new Set([...next.executors,recovery.executor_id])],projectObservedAt:0,projectSequence:0}
            next=projectObservation(next,{...recovery,hip_is_new:false},(event.time??0)/1000)
            continue
          }
          if (value?.schema!==1 || value?.kind!=='executor_binding')
            return {...next,invalid:'Invalid recorded Houdini executor binding'}
          if(next.selectionRecorded)continue // Late legacy context cannot replace a choice or clear.
          if(value.previous_executor!==undefined) {
            if(next.hasOperations||next.recovery||next.identity!==value.previous_executor||!ID.test(value.executor_id))
              return {...next,invalid:'Only an unexecuted task can change its initial target'}
            next={...next,identity:value.executor_id,bindingRecorded:true,executors:[...new Set([...next.executors,value.executor_id])],
              project:{hipPath:null,hipIsNew:null,needsReview:true,sceneId:null,executorId:value.executor_id,sceneEpoch:null,label:null},projectObservedAt:0,projectSequence:0}
            continue
          }
          next=add({...next,bindingRecorded:true},value.executor_id)
        }
        next=projectMessage(next,message,event)
      }
      return next
    }
    const call=executionCall(event)
    if(call&&(call.name==='run_code'||LIVE.has(call.name)))
      state={...state,hasOperations:true}
    // DSH job_output may carry a decoded original live-job execution envelope.
    // Correlate the selected scope at dispatch exactly like a direct call;
    // ordinary generic job output has no Houdini facts and simply clears it.
    if (call && (LIVE.has(call.name)||call.name==='job_output')) return {...state,pending:{...state.pending,[call.callId]:state.identity},
      pendingSelections:{...state.pendingSelections,[call.callId]:state.selectionRevision}}
    const result=executionResult(event)
    if (!result || !Object.hasOwn(state.pending,result.callId)) return state
    const expected=state.pending[result.callId]
    const pending={...state.pending}
    delete pending[result.callId]
    const pendingSelections={...state.pendingSelections};delete pendingSelections[result.callId]
    const next={...state,pending,pendingSelections}
    if(state.execution.current.calls[result.callId]?.name==='job_output'&&result.producer!=='live-job')return next
    const identity=result.value?.execution?.executor_id ?? result.value?.requestReceipt?.executor_id
    if(state.selectionRecorded) {
      const target=state.selectedTarget,execution=result.value?.execution
      const epoch=execution?.scene_epoch??execution?.scene_recovery?.scene_epoch
      const scene=execution?.scene_id??execution?.scene_recovery?.scene_id
      if(!target||state.pendingSelections[result.callId]!==state.selectionRevision||identity!==target.executor_id
        ||execution?.runtime_id!==target.runtime_id||epoch!==target.scene_epoch||scene!==target.scene_id)return next
      const observed=projectObservation(next,execution,execution.observed_at,execution.sequence??0)
      if(observed===next||!observed.project)return observed
      const updated={...target,hip_path:observed.project.hipPath??target.hip_path,
        hip_is_new:observed.project.hipIsNew??target.hip_is_new,
        ...(typeof execution.hip_dir==='string'?{workspace_path:execution.hip_dir}:{})}
      return {...observed,selectedTarget:updated,project:{...observed.project,target:updated}}
    }
    if(identity!==undefined&&expected&&expected!==state.identity)
      return identity===expected?next:{...next,conflict:true}
    return identity===undefined ? next : projectObservation(add(next,identity),result.value?.execution,
      result.value?.execution?.observed_at,result.value?.execution?.sequence??0)
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
  return executorBindingState(projectedExecutorState(ctx,session))
}

/** DSH owns replay, cursor advancement, persistence and invalidation. */
export function projectedExecutorState(ctx:Context,session:{snapshotEvents():readonly SessionEvent[]}):State {
  const state=ctx.get('sessionProjections')?.stateOf(session as Session,'houdiniExecutorIdentity')
  if (!state) throw new Error('Houdini executor identity projection unavailable')
  executorBindingState(state)
  return state
}
export function projectedExecutionFacts(ctx:Context,session:{snapshotEvents():readonly SessionEvent[]}) {
  return executionOutstanding(projectedExecutorState(ctx,session).execution.current)
}


export function projectedExecutorIdentity(ctx:Context,session:Session):string|undefined {
  return projectedExecutorBindingState(ctx,session).identity
}
