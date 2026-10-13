/** Pure executor-identity fold, reused by single and shared Host routing. */
import type {Context} from '@deepseek-ai/cordis'
import type {Session} from '@deepseek-ai/dsh-session'
import type {} from '@deepseek-ai/dsh-session-projection'
import type {} from '@deepseek-ai/dsh-session-projection/types'
import {z} from 'zod'
import {executionCall,executionResult,isHoudiniSource} from './dsh-adapter.js'
import type {SessionEvent} from './execution-history.js'

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
const State=z.object({identity:z.string().nullable(),conflict:z.boolean(),
  invalid:z.string().nullable(),bindingRecorded:z.boolean(),pending:z.record(z.string(),z.string().nullable()),
  executors:z.array(z.string()),recovery:Recovery.nullable(),recoverySeq:z.number()})
type State=z.infer<typeof State>

declare module '@deepseek-ai/dsh-session-projection/types' {
  interface SessionProjectionStateMap {houdiniExecutorIdentity:State}
}

function add(state:State,id:unknown):State {
  if (typeof id!=='string'||!ID.test(id)) return {...state,invalid:'Invalid recorded Houdini executor identity'}
  if (state.identity && state.identity!==id) return {...state,conflict:true}
  return state.identity===id ? state : {...state,identity:id,executors:[...state.executors,id]}
}

export const executorIdentityProjection={
  key:'houdiniExecutorIdentity' as const,stateSchema:State,stateVersion:4,
  init:():State=>({identity:null,conflict:false,invalid:null,bindingRecorded:false,pending:{},
    executors:[],recovery:null,recoverySeq:0}),
  apply(state:State,event:SessionEvent):State {
    const data=event.data
    if (event.type==='user/message' && isHoudiniSource(data?.source)) {
      let next=state
      for (const section of data.source.sections??[]) {
        if (section.name!==TARGET_SECTION) continue
        let value:any
        try {value=JSON.parse(section.text.slice(section.text.indexOf('\n')+1))}
        catch {return {...next,invalid:'Malformed recorded Houdini executor binding'}}
        if(value?.kind==='executor_recovery') {
          const parsed=Recovery.safeParse(value)
          if(!parsed.success||next.invalid||next.conflict||parsed.data.previous_executor!==next.identity)
            return {...next,invalid:'Invalid Houdini recovery transition'}
          const recovery=parsed.data
          next={...next,identity:recovery.executor_id,bindingRecorded:true,recovery,recoverySeq:event.seq??0,
            executors:[...new Set([...next.executors,recovery.executor_id])]}
          continue
        }
        if (value?.schema!==1 || value?.kind!=='executor_binding')
          return {...next,invalid:'Invalid recorded Houdini executor binding'}
        next=add({...next,bindingRecorded:true},value.executor_id)
      }
      return next
    }
    const call=executionCall(event)
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
    return identity===undefined ? next : add(next,identity)
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
