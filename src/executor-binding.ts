/** Target choices are native DSH context, independent of ownership recovery. */
import type {Context} from '@deepseek-ai/cordis'
import {houdiniSnapshot} from './dsh-adapter.js'
import {foldExecutorBinding,projectedExecutorState,executorIdentityProjection,executorBindingState,targetSnapshotSchema,type TargetSnapshot} from './executor-identity-projection.js'
import type {SessionEvent} from './execution-history.js'
import {literalData} from './prompt-data.js'

const TARGET_SECTION='dsh-houdini:executor-binding'
type BindingSession={
  snapshotEvents():readonly SessionEvent[]
  append(type:'user/message',data:ReturnType<typeof houdiniSnapshot>,options:{surfaceOp:'append'}):unknown
}

export function targetSelectionMessage(target:TargetSnapshot|null) {
  return houdiniSnapshot({name:TARGET_SECTION,text:'Houdini operation target selected. Earlier execution results, pending requests and jobs belong to their original target and are historical context, not current scene observations. This changes routing only; it does not load a HIP, move the workspace, claim a writer or grant node ownership.\n'
    +literalData(JSON.stringify({schema:3,kind:'target_selection',target:targetSnapshotSchema.nullable().parse(target)}))})
}
function legacyBindingMessage(current:string,previous?:string) {
  return houdiniSnapshot({name:TARGET_SECTION,text:'Legacy fixed Houdini target.\n'
    +JSON.stringify({schema:1,kind:'executor_binding',executor_id:current,...(previous?{previous_executor:previous}:{})})})
}

/** Fixed developer composition only: record its explicitly configured process.
 * Shared workbench conversations have no pre-step target or recovery hook. */
export function installFixedTargetContext(ctx:Context,current:string):void {
  if(!/^[0-9a-f]{32}$/.test(current))throw new Error('Invalid fixed Houdini executor identity')
  ctx.on('agent/pre-step',async({agent,signal},next)=>{
    const decision=await next()
    signal.throwIfAborted()
    if(decision.kind==='reject')return decision
    let state=projectedExecutorState(ctx,agent.session)
    for(const data of decision.messages)state=executorIdentityProjection.apply(state,{type:'user/message',data})
    executorBindingState(state)
    if(state.bindingRecorded||state.selectionRecorded)return decision
    return {...decision,messages:[...decision.messages,legacyBindingMessage(current)]}
  })
}

export class ExecutorBinding {
  constructor(private readonly stateOf?:((session:BindingSession)=>{identity:string|undefined;bindingRecorded:boolean}),
    private readonly record?:(session:BindingSession,message:ReturnType<typeof houdiniSnapshot>)=>void) {}
  private append(session:BindingSession,message:ReturnType<typeof houdiniSnapshot>) {
    if(this.record)this.record(session,message)
    else session.append('user/message',message,{surfaceOp:'append'})
  }
  async select(session:BindingSession,target:TargetSnapshot|null,signal?:AbortSignal):Promise<void> {
    signal?.throwIfAborted()
    this.append(session,targetSelectionMessage(target))
  }
  async ensure(session:BindingSession,current?:string,signal?:AbortSignal,allowAppend=true):Promise<void> {
    signal?.throwIfAborted()
    if(!this.stateOf)throw new Error('Executor binding requires the current DSH session projection')
    const state=this.stateOf(session)
    requireExecutorContinuityIdentity(state.identity,current)
    if(!current||state.bindingRecorded)return
    if(!/^[0-9a-f]{32}$/.test(current))throw new Error('Invalid Houdini executor identity')
    if(!allowAppend)throw new Error('Houdini target must be selected before model tool calls')
    this.append(session,legacyBindingMessage(current))
  }
}
export function requireExecutorContinuityIdentity(identity:string|undefined,current?:string,reason?:string):void {
  if(identity&&identity!==current)throw new Error('当前对话选择了另一个 Houdini 目标；请明确选择要操作的窗口。'
    +(reason?'\n'+reason:'')+'\nHoudini selected executor differs from this request target')
}
export function recordedExecutorIdentity(events:readonly SessionEvent[]):string|undefined {
  return foldExecutorBinding(events).identity
}
