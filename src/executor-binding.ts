/** Task target binding in the ordinary DSH session. DSH owns persistence. */
import type {Context} from '@deepseek-ai/cordis'
import {houdiniSnapshot} from './dsh-adapter.js'
import {literalData} from './prompt-data.js'
import {foldExecutorBinding,foldExecutorState} from './executor-identity-projection.js'
import type {SessionEvent} from './execution-history.js'
import {lastRecoveryNotice} from './connection-status.js'

const TARGET_SECTION='dsh-houdini:executor-binding'
type BindingSession={
  snapshotEvents():readonly SessionEvent[]
  append(type:'user/message',data:ReturnType<typeof houdiniSnapshot>,options:{surfaceOp:'append'}):unknown
}

function bindingMessage(current:string,previous?:string) {
  return houdiniSnapshot({name:TARGET_SECTION,text:(previous
    ?'Explicit initial target change before any recorded Houdini operation. No scene contents or ownership were restored.\n':'Houdini task target.\n')
    +JSON.stringify({schema:1,kind:'executor_binding',executor_id:current,...(previous?{previous_executor:previous}:{})})})
}

/** The normal step boundary records the target before model-authored tools. */
export function installExecutorBinding(ctx:Context,current?:string):void {
  ctx.on('agent/pre-step',async({agent,signal,messages},next)=>{
    // A successful Save As already authorizes following the current project.
    // Align before inner context providers read cwd and before another model/tool step.
    await ctx.get?.('houdiniRecovery')?.followDirectory?.(agent,signal,messages?.some(message=>message.source?.kind==='user'))
    const decision=await next()
    signal.throwIfAborted()
    if (decision.kind==='reject') return decision
    if(!current) {
      if(!(ctx.get?.('houdiniTargets') as {workbench?:boolean}|undefined)?.workbench)return decision
      if(decision.messages.some(message=>message.source?.kind==='user')) {
        try {
          await ctx.get?.('houdiniRecovery')?.beforeStep(agent,signal)
          const identity=recordedExecutorIdentity(agent.session.snapshotEvents())
          if(lastRecoveryNotice(agent.session.snapshotEvents(),identity))return {...decision,messages:[...decision.messages,
            houdiniSnapshot({name:'dsh-houdini:recovery-required',text:'The continuity check succeeded.\n'
              +literalData(JSON.stringify({executor_id:identity,cleared:true}))})]}
        }
        catch(error) {
          signal.throwIfAborted()
          return {...decision,messages:[...decision.messages,houdiniSnapshot({name:'dsh-houdini:recovery-required',text:
            'The requested Houdini project is unavailable. Discuss the concrete reason; do not substitute another project or replay operations.\n'
            +literalData(JSON.stringify({executor_id:recordedExecutorIdentity(agent.session.snapshotEvents()),reason:error instanceof Error?error.message:String(error)}))})]}
        }
      }
      return decision
    }
    let recoveryFailure:unknown
    let recoveryChecked=false
    if(decision.messages.some(message=>message.source?.kind==='user')) {
      try {
        const recovery=ctx.get?.('houdiniRecovery')
        if(recovery){await recovery.beforeStep(agent,signal);recoveryChecked=true}
      }
      catch(error){signal.throwIfAborted();recoveryFailure=error}
    }
    const proposed=[...agent.session.snapshotEvents(),...decision.messages.map(data=>({type:'user/message',data}))]
    let state:ReturnType<typeof foldExecutorBinding>
    let checkingIdentity=false
    try {
      if(recoveryFailure)throw recoveryFailure
      state=foldExecutorBinding(proposed)
      checkingIdentity=true
      requireExecutorContinuityIdentity(state.identity,current)
    } catch(error) {
      signal.throwIfAborted()
      const reason=checkingIdentity?(lastRecoveryNotice(proposed,current)?.reason??(error instanceof Error?error.message:String(error))):
        error instanceof Error?error.message:String(error)
      const notice={name:'dsh-houdini:recovery-required',text:
        'Houdini automatic continuity check could not safely complete. Conversation and historical material remain available; live tools remain blocked. '
        +'Explain the concrete facts below and handle any actual project/content choice in conversation. Never ask the user to click repair/recovery controls or to confirm technical success. Do not replay old requests or bypass ownership.\n'
        +literalData(JSON.stringify({executor_id:current,reason}))}
      const recorded=lastRecoveryNotice(proposed,current)?.reason===reason
      return recorded?decision:{...decision,messages:[...decision.messages,houdiniSnapshot(notice)]}
    }
    const nextMessages=recoveryChecked&&lastRecoveryNotice(proposed,current)?[...decision.messages,houdiniSnapshot({name:'dsh-houdini:recovery-required',text:
      'The continuity check for this input no longer reports the previous failure. Each live operation still verifies the scene.\n'
      +literalData(JSON.stringify({executor_id:current,cleared:true}))})]:decision.messages
    if (state.bindingRecorded) return {...decision,messages:nextMessages}
    if (!/^[0-9a-f]{32}$/.test(current)) throw new Error('Invalid Houdini executor identity')
    return {...decision,messages:[...nextMessages,bindingMessage(current)]}
  })
}

export class ExecutorBinding {
  constructor(private readonly stateOf:(session:BindingSession)=>{identity:string|undefined;bindingRecorded:boolean}
    = session=>foldExecutorBinding(session.snapshotEvents()),
    private readonly record?:(session:BindingSession,message:ReturnType<typeof bindingMessage>)=>void) {}

  async reselectUnexecuted(session:BindingSession,current:string,signal?:AbortSignal):Promise<void> {
    signal?.throwIfAborted()
    const state=foldExecutorState(session.snapshotEvents())
    if(!state.identity||state.identity===current)return this.ensure(session,current,signal)
    if(state.hasOperations||state.recovery||!/^[0-9a-f]{32}$/.test(current))throw new Error('已有现场操作的对话必须通过保存点接续，不能直接换绑。')
    const message=bindingMessage(current,state.identity)
    if(this.record)this.record(session,message)
    else session.append('user/message',message,{surfaceOp:'append'})
  }

  async ensure(session:BindingSession,current?:string,signal?:AbortSignal,allowAppend=true):Promise<void> {
    signal?.throwIfAborted()
    const state=this.stateOf(session)
    requireExecutorContinuityIdentity(state.identity,current,lastRecoveryNotice(session.snapshotEvents(),current)?.reason)
    if (!current || state.bindingRecorded) return
    if (!/^[0-9a-f]{32}$/.test(current)) throw new Error('Invalid Houdini executor identity')
    if (!allowAppend) throw new Error('Houdini target must be selected before model tool calls')
    if(this.record)this.record(session,bindingMessage(current))
    else session.append('user/message',bindingMessage(current),{surfaceOp:'append'})
  }
}

export function requireExecutorContinuity(events:readonly SessionEvent[],current?:string):void {
  requireExecutorContinuityIdentity(recordedExecutorIdentity(events),current)
}

export function requireExecutorContinuityIdentity(identity:string|undefined,current?:string,reason?:string):void {
  if (identity && identity!==current) throw new Error('这段对话还没有接回当前 Houdini，本次操作没有发送到工程。'
    +(reason?'\n接续未完成的原因：'+reason:'\n请在对话中说明要继续哪份工程；发送消息后系统会核对接续条件。')
    +'\n技术信息：Houdini task requires recovery: recorded executor differs from the selected target')
}

export function recordedExecutorIdentity(events:readonly SessionEvent[]):string|undefined {
  return foldExecutorBinding(events).identity
}
