/** Host-only fold of recorded executor identity. No live discovery or ownership. */
import type {Context} from '@deepseek-ai/cordis'
import type {Session} from '@deepseek-ai/dsh-session'
import type {} from '@deepseek-ai/dsh-session-projection'
import type {} from '@deepseek-ai/dsh-session-projection/types'
import {z} from 'zod'

const TARGET_SECTION='dsh-houdini:executor-binding'
const TOOLS=new Set(['houdini_exec','houdini_query','houdini_job_submit',
  'houdini_job_status','houdini_job_cancel'])
const ID=/^[0-9a-f]{32}$/
const State=z.object({identity:z.string().nullable(),conflict:z.boolean(),
  invalid:z.string().nullable(),bindingRecorded:z.boolean(),pending:z.record(z.string(),z.boolean()),
  seen:z.record(z.string(),z.boolean())})
type State=z.infer<typeof State>

declare module '@deepseek-ai/dsh-session-projection/types' {
  interface SessionProjectionStateMap {
    houdiniExecutorIdentity: State
  }
}

function add(state:State,id:unknown):State {
  if(typeof id!=='string'||!ID.test(id))
    return {...state,invalid:'Invalid recorded Houdini executor identity; no live request sent. Inspect the original session evidence.'}
  if(state.identity && state.identity!==id)return {...state,conflict:true}
  return state.identity===id?state:{...state,identity:id}
}

export const executorIdentityProjection={
  key:'houdiniExecutorIdentity' as const,
  stateSchema:State,
  stateVersion:2,
  init:():State=>({identity:null,conflict:false,invalid:null,bindingRecorded:false,pending:{},seen:{}}),
  apply(state:State,event:any):State {
    const data=event.data
    if(event.type==='user/message' && data?.source?.kind==='plugin'
        && data.source.plugin==='dsh-houdini') {
      let next=state
      for(const section of data.source.sections||[]) {
        if(section.name!==TARGET_SECTION)continue
        let value:any
        try {value=JSON.parse(section.text.slice(section.text.indexOf('\n')+1))}
        catch {return {...next,invalid:'Malformed persisted executor binding; no live request sent'}}
        if(value?.schema!==1||value?.kind!=='executor_binding'||!ID.test(value?.executor_id||''))
          return {...next,invalid:'Invalid persisted executor binding; no live request sent'}
        next=add({...next,bindingRecorded:true},value.executor_id)
      }
      return next
    }
    if(event.type==='tool/call' && TOOLS.has(data?.name)
        && typeof data?.callId==='string') {
      if(Object.hasOwn(state.seen,data.callId))return state
      const eligible=!(data.name==='houdini_query'
        && (data.args?.result_ref||data.args?.source_ref||data.args?.request_ref))
      return {...state,pending:{...state.pending,[data.callId]:eligible}}
    }
    if(event.type!=='tool/result')return state
    const callId=data?.message?.source?.callId
    if(typeof callId!=='string'||!Object.hasOwn(state.pending,callId))return state
    const eligible=state.pending[callId]
    const pending={...state.pending}
    delete pending[callId]
    const next={...state,pending,seen:{...state.seen,[callId]:true}}
    if(!eligible)return next
    const identity=data.meta?.canonical?.execution?.executor_id
      ??data.meta?.canonical?.requestReceipt?.executor_id
    return identity===undefined?next:add(next,identity)
  },
}

export function registerExecutorIdentityProjection(ctx:Context):void {
  ctx.sessionProjections.register(executorIdentityProjection)
}

export function projectedExecutorBindingState(ctx:Context,session:Session):{identity:string|undefined;bindingRecorded:boolean} {
  const registry=ctx.get('sessionProjections')
  if(!registry)throw new Error('Executor identity projection unavailable; no live request sent')
  const state=registry.stateOf(session,'houdiniExecutorIdentity')
  if(!state)throw new Error('Executor identity projection unavailable; no live request sent')
  if(state.invalid)throw new Error(state.invalid)
  if(state.conflict)throw new Error('Houdini task requires recovery: history contains more than one recorded executor identity. No live request sent. Cross-process recovery is not implemented: read retained results, preserve the saved/crash HIP and reconcile the project before any future recovery flow; do not start a new task to bypass this check or infer ownership from the HIP path.')
  return {identity:state.identity??undefined,bindingRecorded:state.bindingRecorded}
}

export function projectedExecutorIdentity(ctx:Context,session:Session):string|undefined {
  return projectedExecutorBindingState(ctx,session).identity
}
