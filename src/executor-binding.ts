/** Task target binding in the ordinary DSH session. DSH owns persistence. */
import type {Context} from '@deepseek-ai/cordis'
import {houdiniSnapshot,isHoudiniSource} from './dsh-adapter.js'
import {literalData} from './prompt-data.js'
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
  ctx.on('agent/pre-step',async({agent,signal,messages},next)=>{
    // A successful Save As already authorizes following the current project.
    // Align before inner context providers read cwd and before another model/tool step.
    await ctx.get?.('houdiniRecovery')?.followDirectory?.(agent,signal,messages?.some(message=>message.source?.kind==='user'))
    const decision=await next()
    signal.throwIfAborted()
    if (decision.kind==='reject'||!current) return decision
    let recoveryFailure:unknown
    if(decision.messages.some(message=>message.source?.kind==='user')) {
      try {await ctx.get?.('houdiniRecovery')?.beforeStep(agent,signal)}
      catch(error){signal.throwIfAborted();recoveryFailure=error}
    }
    const proposed=[...agent.session.snapshotEvents(),...decision.messages.map(data=>({type:'user/message',data}))]
    let state:ReturnType<typeof foldExecutorBinding>
    try {
      if(recoveryFailure)throw recoveryFailure
      state=foldExecutorBinding(proposed)
      requireExecutorContinuityIdentity(state.identity,current)
    } catch(error) {
      signal.throwIfAborted()
      const notice={name:'dsh-houdini:recovery-required',text:
        'Houdini automatic continuity check could not safely complete. Conversation and historical material remain available; live tools remain blocked. '
        +'Explain the concrete facts below and handle any actual project/content choice in conversation. Never ask the user to click repair/recovery controls or to confirm technical success. Do not replay old requests or bypass ownership.\n'
        +literalData(JSON.stringify({executor_id:current,reason:error instanceof Error?error.message:String(error)}))}
      const recorded=proposed.some(event=>{
        if(event.type!=='user/message')return false
        const source=event.data?.source as {sections?:Array<{name:string;text:string}>}|undefined
        return isHoudiniSource(source)
          &&source?.sections?.some(section=>section.name===notice.name&&section.text===notice.text)
      })
      return recorded?decision:{...decision,messages:[...decision.messages,houdiniSnapshot(notice)]}
    }
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
  if (identity && identity!==current) throw new Error('系统尚未完成工程接续。请依据本轮连接诊断在对话中处理工程选择；不要让用户点击修复按钮或口头确认技术成功。Houdini task requires recovery: recorded executor differs from the selected target')
}

export function recordedExecutorIdentity(events:readonly SessionEvent[]):string|undefined {
  return foldExecutorBinding(events).identity
}
