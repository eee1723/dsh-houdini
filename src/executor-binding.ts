/** Task target binding in the ordinary DSH session. DSH owns persistence. */
import type {Context} from '@deepseek-ai/cordis'
import {houdiniSnapshot} from './dsh-adapter.js'
import {foldExecutorBinding} from './executor-identity-projection.js'
import type {SessionEvent} from './execution-history.js'

const TARGET_SECTION='dsh-houdini:executor-binding'
type BindingSession={
  snapshotEvents():readonly SessionEvent[]
  append(type:'user/message',data:ReturnType<typeof houdiniSnapshot>,options:{surfaceOp:'append'}):unknown
}

function bindingMessage(current:string) {
  return houdiniSnapshot({name:TARGET_SECTION,text:'Houdini task target.\n'
    +JSON.stringify({schema:1,kind:'executor_binding',executor_id:current})})
}

/** The normal step boundary records the target before model-authored tools. */
export function installExecutorBinding(ctx:Context,current?:string):void {
  ctx.on('agent/pre-step',async({agent,signal},next)=>{
    const decision=await next()
    signal.throwIfAborted()
    if (decision.kind==='reject'||!current) return decision
    const proposed=[...agent.session.snapshotEvents(),...decision.messages.map(data=>({type:'user/message',data}))]
    const state=foldExecutorBinding(proposed)
    requireExecutorContinuityIdentity(state.identity,current)
    if (state.bindingRecorded) return decision
    if (!/^[0-9a-f]{32}$/.test(current)) throw new Error('Invalid Houdini executor identity')
    return {...decision,messages:[...decision.messages,bindingMessage(current)]}
  })
}

export class ExecutorBinding {
  constructor(private readonly stateOf:(session:BindingSession)=>{identity:string|undefined;bindingRecorded:boolean}
    = session=>foldExecutorBinding(session.snapshotEvents())) {}

  async ensure(session:BindingSession,current?:string,signal?:AbortSignal,allowAppend=true):Promise<void> {
    signal?.throwIfAborted()
    const state=this.stateOf(session)
    requireExecutorContinuityIdentity(state.identity,current)
    if (!current || state.bindingRecorded) return
    if (!/^[0-9a-f]{32}$/.test(current)) throw new Error('Invalid Houdini executor identity')
    if (!allowAppend) throw new Error('Houdini target must be selected before model tool calls')
    session.append('user/message',bindingMessage(current),{surfaceOp:'append'})
  }
}

export function requireExecutorContinuity(events:readonly SessionEvent[],current?:string):void {
  requireExecutorContinuityIdentity(recordedExecutorIdentity(events),current)
}

export function requireExecutorContinuityIdentity(identity:string|undefined,current?:string):void {
  if (identity && identity!==current) throw new Error('Houdini task requires recovery: recorded executor differs from the selected target')
}

export function recordedExecutorIdentity(events:readonly SessionEvent[]):string|undefined {
  return foldExecutorBinding(events).identity
}
