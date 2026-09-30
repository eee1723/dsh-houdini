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
const State=z.object({identity:z.string().nullable(),conflict:z.boolean(),
  invalid:z.string().nullable(),bindingRecorded:z.boolean(),pending:z.record(z.string(),z.boolean())})
type State=z.infer<typeof State>

declare module '@deepseek-ai/dsh-session-projection/types' {
  interface SessionProjectionStateMap {houdiniExecutorIdentity:State}
}

function add(state:State,id:unknown):State {
  if (typeof id!=='string'||!ID.test(id)) return {...state,invalid:'Invalid recorded Houdini executor identity'}
  if (state.identity && state.identity!==id) return {...state,conflict:true}
  return state.identity===id ? state : {...state,identity:id}
}

export const executorIdentityProjection={
  key:'houdiniExecutorIdentity' as const,stateSchema:State,stateVersion:3,
  init:():State=>({identity:null,conflict:false,invalid:null,bindingRecorded:false,pending:{}}),
  apply(state:State,event:SessionEvent):State {
    const data=event.data
    if (event.type==='user/message' && isHoudiniSource(data?.source)) {
      let next=state
      for (const section of data.source.sections??[]) {
        if (section.name!==TARGET_SECTION) continue
        let value:any
        try {value=JSON.parse(section.text.slice(section.text.indexOf('\n')+1))}
        catch {return {...next,invalid:'Malformed recorded Houdini executor binding'}}
        if (value?.schema!==1 || value?.kind!=='executor_binding')
          return {...next,invalid:'Invalid recorded Houdini executor binding'}
        next=add({...next,bindingRecorded:true},value.executor_id)
      }
      return next
    }
    const call=executionCall(event)
    if (call && LIVE.has(call.name)) return {...state,pending:{...state.pending,[call.callId]:true}}
    const result=executionResult(event)
    if (!result || !Object.hasOwn(state.pending,result.callId)) return state
    const pending={...state.pending}
    delete pending[result.callId]
    const next={...state,pending}
    const identity=result.value?.execution?.executor_id ?? result.value?.requestReceipt?.executor_id
    return identity===undefined ? next : add(next,identity)
  },
}

export function executorBindingState(state:State):{identity:string|undefined;bindingRecorded:boolean} {
  if (state.invalid) throw new Error(state.invalid)
  if (state.conflict) throw new Error('Houdini task requires recovery: history records more than one executor identity')
  return {identity:state.identity??undefined,bindingRecorded:state.bindingRecorded}
}

export function foldExecutorBinding(events:readonly SessionEvent[]) {
  let state=executorIdentityProjection.init()
  for (const event of events) state=executorIdentityProjection.apply(state,event)
  return executorBindingState(state)
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
